# -*- coding: utf-8 -*-
"""
A/B test: baseline (A) vs baseline + deterministic hard-check gate (H, medium).

Medium gate: chains failing hard checks (empty_reasoning / multi_answer_conflict)
are excluded from the message-passing graph and from pooling entirely; the
remaining valid nodes re-run the SAME baseline pipeline (pairwise_margin +
1-round message passing + weighted-mean pooling).

Control variables: frozen initial responses, same pipeline, same seeds.
"""

import json
import os
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from teacher_validation import (
    make_unique_node_names,
    run_baseline,
    _extract_letter,
    _sanitize,
    REF_MODELS,
    META,
    TEMP,
    MAX_TOKENS,
    SEED,
    make_instruction,
)
from hard_check import hard_check_chain, veto_flags


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


def _subset(cfg, valid):
    """Rebuild config dicts on a subset of node indices (reindexed 0..n-1)."""
    # NOTE: message_passing indexes model_endpoint_dict by MODEL NAME, while
    # initial_responses / model_name_idx are indexed by 0..n-1 (same convention
    # as the full 3-node pipeline where models_dict is keyed by unique names).
    valid_names = [cfg["model_name_idx"][old_i] for old_i in sorted(valid)]
    models_sub = {name: cfg["models_dict_unique"][name] for name in valid_names}
    idx_map = {}
    for new_i, old_i in enumerate(sorted(valid)):
        idx_map[new_i] = old_i
    resp_sub = {new_i: cfg["initial_responses"][old_i] for new_i, old_i in idx_map.items()}
    name_idx_sub = {new_i: name for new_i, name in enumerate(valid_names)}
    return models_sub, name_idx_sub, resp_sub, idx_map


def run_one_hard(item, initials_by_idx):
    cfg = _rebuild(item, initials_by_idx)
    result = {
        "idx": cfg["idx"], "gold": cfg["gold"],
        "sampled_nodes": cfg["sampled_nodes"], "unique_names": cfg["unique_names"],
        "initial_answers": cfg["initial_answers"],
        "initial_responses": cfg["initial_responses"],
    }
    t0 = time.time()

    # Condition A: full baseline on all 3 nodes (matched, same process)
    try:
        fa, score_a, note_a = run_baseline(
            cfg["models_dict_unique"], cfg["model_name_idx"],
            cfg["initial_responses"], None, cfg["instruction"],
        )
        result["A"] = {"answer": _extract_letter(fa), "final_response": fa,
                       "pool_note": note_a, "score_dict": score_a}
    except Exception as e:
        result["A"] = {"error": str(e)}
        print(f"[{cfg['idx']}] A error: {e}", flush=True)

    # Hard checks on the ORIGINAL chains
    flags_by_node = {}
    vetoed = []
    for i in range(len(cfg["unique_names"])):
        fl = hard_check_chain(cfg["initial_responses"][i])
        flags_by_node[i] = fl
        if veto_flags(fl):
            vetoed.append(i)
    valid = [i for i in range(len(cfg["unique_names"])) if i not in vetoed]
    result["flags_by_node"] = flags_by_node
    result["vetoed"] = vetoed

    # Condition H: re-run the same baseline on the valid subset
    try:
        if not vetoed:
            result["H"] = {"answer": result["A"].get("answer"), "note": "no_veto"}
        elif len(valid) == 1:
            only = valid[0]
            ans = _extract_letter(cfg["initial_responses"][only])
            result["H"] = {"answer": ans, "note": "veto_single",
                           "survivor": only, "survivor_model": cfg["model_name_idx"][only]}
        else:
            models_sub, name_idx_sub, resp_sub, idx_map = _subset(cfg, valid)
            fh, score_h, note_h = run_baseline(
                models_sub, name_idx_sub, resp_sub, None, cfg["instruction"],
            )
            result["H"] = {"answer": _extract_letter(fh), "final_response": fh,
                           "pool_note": note_h, "score_dict": score_h,
                           "note": "veto_subset", "subset": [idx_map[i] for i in sorted(idx_map)]}
    except Exception as e:
        result["H"] = {"error": str(e)}
        print(f"[{cfg['idx']}] H error: {e}", flush=True)

    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{cfg['idx']}] done in {result['time_s']}s | gold={cfg['gold']} | "
          f"A={result.get('A', {}).get('answer')} H={result.get('H', {}).get('answer')} "
          f"vetoed={vetoed} flags={flags_by_node}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--idxs_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reuse_initials", required=True)
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    with open(args.idxs_path) as f:
        idxs = json.load(f)
    subset = [dict(s, idx=i) for i, s in enumerate(samples) if i in idxs]
    if args.limit:
        subset = subset[: args.limit]
    print(f"[HardAB] questions: {len(subset)}", flush=True)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.reuse_initials) as f:
        old_results = json.load(f)
    initials_by_idx = {r["idx"]: r for r in old_results}

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one_hard, item, initials_by_idx): item["idx"] for item in subset}
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
            print(f"[HardAB] progress {done}/{len(subset)}", flush=True)
    print(f"[HardAB] saved {len(results)} results to {args.out}", flush=True)


if __name__ == "__main__":
    main()
