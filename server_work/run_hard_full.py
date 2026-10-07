# -*- coding: utf-8 -*-
"""
Full-198 hard-check A/B/W/H experiment.

For EVERY question, in the SAME process (matched):
  A = baseline (pairwise_margin + 1-round message passing + weighted-mean pooling)
  W = weak hard-check: vetoed chains' weights x0.5, all nodes participate
  H = medium hard-check: vetoed chains excluded, remaining subset re-runs baseline
W and H are only computed when hard checks flag a chain; otherwise W = H = A.

Control: identical initial chains per question (freshly generated, frozen within
the question), same pipeline, same seeds. Only the gate differs.
"""

import json
import os
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from teacher_validation import (
    node_sampling_model_card,
    generate_initial_response_with_confidence,
    make_unique_node_names,
    _extract_letter,
    _sanitize,
    REF_MODELS,
    META,
    TEMP,
    MAX_TOKENS,
    SEED,
    TOP_K,
    make_instruction,
)
from hard_check import hard_check_chain, veto_flags
from run_hard_weak import _run_baseline_like, WEAK_SCALE


def _sample_and_answer(item):
    idx = item["idx"]
    question = item["question"]
    gold = item["gold_answer"]
    instruction = make_instruction(question)
    result = {"idx": idx, "gold": gold}

    meta_cfg = model_endpoint_dict[META]
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    sampled_nodes, _fallback, _it, _ot = node_sampling_model_card(
        model=meta_cfg["model_id"], endpoint=meta_cfg["url"], messages=[instruction],
        model_info_dict=models_dict, top_k=TOP_K, temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
    )
    unique_names, unique_to_original = make_unique_node_names(sampled_nodes)
    models_dict_unique = {un: models_dict[unique_to_original[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    initial_responses, confidences = {}, {}
    for i, un in enumerate(unique_names):
        raw, ans, conf, _it, _ot = generate_initial_response_with_confidence(
            model_id=models_dict_unique[un]["model_id"], endpoint=models_dict_unique[un]["url"],
            instruction=instruction, data="GPQA", num_choice=4,
            temperature=TEMP, max_tokens=MAX_TOKENS, seed=SEED,
            debug_txt=f"[Initial {un}] ",
        )
        initial_responses[i] = raw
        confidences[i] = conf

    result["sampled_nodes"] = sampled_nodes
    result["unique_names"] = unique_names
    result["initial_responses"] = initial_responses
    result["initial_answers"] = {i: _extract_letter(r) for i, r in initial_responses.items()}

    # hard-check flags
    flags_by_node = {}
    vetoed = []
    for i in range(len(unique_names)):
        fl = hard_check_chain(initial_responses[i])
        flags_by_node[i] = fl
        if veto_flags(fl):
            vetoed.append(i)
    result["flags_by_node"] = flags_by_node
    result["vetoed"] = vetoed

    # Condition A: baseline
    try:
        fa, score_a, note_a, _ = _run_baseline_like(
            models_dict_unique, model_name_idx, initial_responses, instruction, scale=None,
        )
        result["A"] = {"answer": _extract_letter(fa), "final_response": fa,
                       "pool_note": note_a, "score_dict": score_a}
    except Exception as e:
        result["A"] = {"error": str(e)}
        print(f"[{idx}] A error: {e}", flush=True)

    if vetoed:
        # Condition W: weak (weight x0.5), all nodes participate
        try:
            scale = {i: WEAK_SCALE for i in vetoed}
            fw, score_w, note_w, sdw = _run_baseline_like(
                models_dict_unique, model_name_idx, initial_responses, instruction, scale=scale,
            )
            result["W"] = {"answer": _extract_letter(fw), "final_response": fw,
                           "pool_note": note_w, "score_dict": sdw, "note": "weak_scale",
                           "scaled_nodes": vetoed}
        except Exception as e:
            result["W"] = {"error": str(e)}
            print(f"[{idx}] W error: {e}", flush=True)

        # Condition H: medium (exclude vetoed nodes, re-run baseline on subset)
        try:
            valid = [i for i in range(len(unique_names)) if i not in vetoed]
            if len(valid) == 1:
                result["H"] = {"answer": _extract_letter(initial_responses[valid[0]]),
                               "note": "veto_single", "subset": valid}
            else:
                valid_names = [model_name_idx[i] for i in sorted(valid)]
                models_sub = {n: models_dict_unique[n] for n in valid_names}
                idx_map = {new_i: old_i for new_i, old_i in enumerate(sorted(valid))}
                resp_sub = {new_i: initial_responses[old_i] for new_i, old_i in idx_map.items()}
                name_idx_sub = {new_i: n for new_i, n in enumerate(valid_names)}
                fh, score_h, note_h, _ = _run_baseline_like(
                    models_sub, name_idx_sub, resp_sub, instruction, scale=None,
                )
                result["H"] = {"answer": _extract_letter(fh), "final_response": fh,
                               "score_dict": score_h, "note": "veto_subset", "subset": sorted(valid)}
        except Exception as e:
            result["H"] = {"error": str(e)}
            print(f"[{idx}] H error: {e}", flush=True)
    else:
        # no veto: W = H = A by design
        result["W"] = {"answer": result.get("A", {}).get("answer"), "note": "no_veto"}
        result["H"] = {"answer": result.get("A", {}).get("answer"), "note": "no_veto"}

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    items = [dict(s, idx=i) for i, s in enumerate(samples)]
    if args.limit:
        items = items[: args.limit]
    print(f"[HardFull] questions: {len(items)}", flush=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_sample_and_answer, item): item["idx"] for item in items}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                r = fut.result()
                results.append(_sanitize(r))
                with open(args.out, "w") as f:
                    json.dump(results, f, ensure_ascii=False, indent=1)
            except Exception as e:
                print(f"[worker] fatal: {e}", flush=True)
            print(f"[HardFull] progress {done}/{len(items)}", flush=True)
    print(f"[HardFull] saved {len(results)} results to {args.out}", flush=True)


if __name__ == "__main__":
    main()
