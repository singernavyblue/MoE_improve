# -*- coding: utf-8 -*-
"""
Weak hard-check A/B: baseline (A) vs baseline + weight-halving (W).

W: chains that fail hard checks (empty_reasoning / multi_answer_conflict) are NOT
removed; their pairwise-margin weights are simply multiplied by 0.5 and the whole
weight vector is renormalized before message passing and pooling. All nodes still
participate (minimal perturbation).

Control: frozen initial responses, same pipeline, same process (A and W paired).
"""

import json
import os
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from modules import edge_sampling, message_passing, graph_pooling
from teacher_validation import (
    make_unique_node_names,
    _extract_letter,
    _sanitize,
    REF_MODELS,
    META,
    TEMP,
    MAX_TOKENS,
    SEED,
    THRESHOLD,
    ROUNDS,
    FINAL_PROMPT,
    make_instruction,
)
from hard_check import hard_check_chain, veto_flags

WEAK_SCALE = 0.5


def _run_baseline_like(models_dict_unique, model_name_idx, initial_responses, instruction,
                       scale=None, judge_model=None, edge_mode="pairwise_margin"):
    """Same body as teacher_validation.run_baseline, with optional per-node weight scale
    and optional judge_model override for edge_sampling (e.g. "deepseek")."""
    output = edge_sampling(
        models_dict=models_dict_unique,
        model_name_idx=model_name_idx,
        initial_responses=initial_responses,
        messages=[instruction],
        threshold=THRESHOLD,
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        seed=SEED,
        confidences=None,
        edge_mode=edge_mode,
        judge_model=judge_model,
    )
    meta_cfg = model_endpoint_dict[META]
    if not isinstance(output, tuple):
        final_response, _, _ = graph_pooling(
            model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
            refined_response=initial_responses, messages=[instruction],
            temperature=TEMP, max_tokens=MAX_TOKENS, final_prompt=FINAL_PROMPT, seed=SEED,
        )
        return final_response, {}, "fallback_mean", None

    source_edges, target_edges, score_dict, _sm, _fb, _fbe, _it, _ot, target_weights = output
    if scale:
        sd2 = {k: float(v) * scale.get(int(k), 1.0) for k, v in score_dict.items()}
        tot = sum(sd2.values())
        if tot > 0:
            score_dict = {k: v / tot for k, v in sd2.items()}

    round_responses = dict(initial_responses)
    for _round in range(ROUNDS):
        _s2t, t2s, _it, _ot = message_passing(
            model_endpoint_dict=models_dict_unique,
            model_name_idx=model_name_idx,
            initial_responses=round_responses,
            source_edges=source_edges,
            target_edges=target_edges,
            score_dict=score_dict,
            source_with_most_edges=None,
            messages=[instruction],
            temperature=TEMP,
            max_tokens=MAX_TOKENS,
            round=f"{_round + 1}/{ROUNDS}",
            final_prompt=FINAL_PROMPT,
            seed=SEED,
            target_weights=target_weights,
            anti_sycophancy=False,
        )
        round_responses = dict(t2s)

    final_response, _, _ = graph_pooling(
        model=meta_cfg["model_id"], endpoint=meta_cfg["url"],
        refined_response=round_responses, weights=score_dict, messages=[instruction],
        temperature=TEMP, max_tokens=MAX_TOKENS, final_prompt=FINAL_PROMPT, seed=SEED,
    )
    return final_response, score_dict, "goa", score_dict


def _rebuild(item, initials_by_idx):
    old = initials_by_idx.get(item["idx"])
    if not old:
        raise ValueError(f"no frozen initials for idx {item['idx']}")
    idx = item["idx"]
    question = item["question"]
    gold = item["gold_answer"]
    instruction = make_instruction(question)

    sampled_nodes = old["sampled_nodes"]
    unique_names = old["unique_names"]
    initial_responses = {int(k): v for k, v in sorted(old["initial_responses"].items())}
    initial_answers = {int(k): v for k, v in sorted((old.get("initial_answers") or {}).items())}
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    _u_names, u_to_orig = make_unique_node_names(sampled_nodes)
    models_dict_unique = {un: models_dict[u_to_orig[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))
    return {
        "idx": idx, "gold": gold, "instruction": instruction,
        "sampled_nodes": sampled_nodes, "unique_names": unique_names,
        "initial_responses": initial_responses, "initial_answers": initial_answers,
        "models_dict_unique": models_dict_unique, "model_name_idx": model_name_idx,
    }


def run_one_weak(item, initials_by_idx):
    cfg = _rebuild(item, initials_by_idx)
    result = {
        "idx": cfg["idx"], "gold": cfg["gold"],
        "sampled_nodes": cfg["sampled_nodes"], "unique_names": cfg["unique_names"],
        "initial_answers": cfg["initial_answers"],
        "initial_responses": cfg["initial_responses"],
    }
    t0 = time.time()

    # hard-check flags
    flags_by_node = {}
    vetoed = []
    for i in range(len(cfg["unique_names"])):
        fl = hard_check_chain(cfg["initial_responses"][i])
        flags_by_node[i] = fl
        if veto_flags(fl):
            vetoed.append(i)
    result["flags_by_node"] = flags_by_node
    result["vetoed"] = vetoed

    try:
        fa, score_a, note_a, _ = _run_baseline_like(
            cfg["models_dict_unique"], cfg["model_name_idx"], cfg["initial_responses"],
            cfg["instruction"], scale=None,
        )
        result["A"] = {"answer": _extract_letter(fa), "final_response": fa,
                       "pool_note": note_a, "score_dict": score_a}
    except Exception as e:
        result["A"] = {"error": str(e)}
        print(f"[{cfg['idx']}] A error: {e}", flush=True)

    try:
        if not vetoed:
            result["W"] = {"answer": result["A"].get("answer"), "note": "no_veto",
                           "score_dict": result["A"].get("score_dict")}
        else:
            scale = {i: WEAK_SCALE for i in vetoed}
            fw, score_w, note_w, sdw = _run_baseline_like(
                cfg["models_dict_unique"], cfg["model_name_idx"], cfg["initial_responses"],
                cfg["instruction"], scale=scale,
            )
            result["W"] = {"answer": _extract_letter(fw), "final_response": fw,
                           "pool_note": note_w, "score_dict": sdw,
                           "note": "weak_scale", "scaled_nodes": vetoed}
    except Exception as e:
        result["W"] = {"error": str(e)}
        print(f"[{cfg['idx']}] W error: {e}", flush=True)

    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{cfg['idx']}] done in {result['time_s']}s | gold={cfg['gold']} | "
          f"A={result.get('A', {}).get('answer')} W={result.get('W', {}).get('answer')} "
          f"vetoed={vetoed}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--idxs_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reuse_initials", required=True)
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    with open(args.idxs_path) as f:
        idxs = json.load(f)
    subset = [dict(s, idx=i) for i, s in enumerate(samples) if i in idxs]
    print(f"[HardWeak] questions: {len(subset)}", flush=True)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.reuse_initials) as f:
        old_results = json.load(f)
    initials_by_idx = {r["idx"]: r for r in old_results}

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one_weak, item, initials_by_idx): item["idx"] for item in subset}
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
            print(f"[HardWeak] progress {done}/{len(subset)}", flush=True)
    print(f"[HardWeak] saved {len(results)} results to {args.out}", flush=True)


if __name__ == "__main__":
    main()
