# -*- coding: utf-8 -*-
"""
Live validation on the 22 "judge-top = gold chain but meta lost" questions.

Mechanism under test: final answer = letter of the judge's HIGHEST-weight chain
that passes the hard-check gate (no meta message passing / pooling needed).

Control: SAME frozen initial chains as hard_full_198.json (which also stores the
matched baseline A answers). Judge scores are re-computed fresh by Prometheus.
"""

import json
import os
import time
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from modules import edge_sampling
from teacher_validation import (
    make_unique_node_names,
    _extract_letter,
    _sanitize,
    REF_MODELS,
    TEMP,
    MAX_TOKENS,
    SEED,
    THRESHOLD,
    make_instruction,
)
from hard_check import hard_check_chain, veto_flags

CAT22 = [0, 1, 8, 14, 25, 31, 42, 56, 61, 74, 92, 120, 129, 134, 138, 140, 142, 150, 166, 174, 178, 197]


def run_one(rec):
    idx = rec["idx"]
    gold = rec["gold"]
    instruction = make_instruction(rec["question"])
    result = {"idx": idx, "gold": gold,
              "stored_A": (rec.get("A") or {}).get("answer"),
              "stored_weights": (rec.get("A") or {}).get("score_dict")}
    t0 = time.time()

    unique_names = rec["unique_names"]
    initial_responses = {int(k): v for k, v in rec["initial_responses"].items()}
    initial_answers = {int(k): v for k, v in (rec.get("initial_answers") or {}).items()}
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}
    _u, u_to_orig = make_unique_node_names(rec["sampled_nodes"])
    models_dict_unique = {un: models_dict[u_to_orig[un]] for un in unique_names}
    model_name_idx = dict(enumerate(unique_names))

    # hard-check gate on original chains
    vetoed = []
    for i in range(len(unique_names)):
        if veto_flags(hard_check_chain(initial_responses[i])):
            vetoed.append(i)
    result["vetoed"] = vetoed

    # fresh judge pairwise-margin scores (same pipeline as baseline scoring)
    out = edge_sampling(
        models_dict=models_dict_unique,
        model_name_idx=model_name_idx,
        initial_responses=initial_responses,
        messages=[instruction],
        threshold=THRESHOLD,
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        seed=SEED,
        confidences=None,
        edge_mode="pairwise_margin",
    )
    if not isinstance(out, tuple):
        result["error"] = f"edge_sampling returned non-tuple: {type(out)}"
        result["time_s"] = round(time.time() - t0, 1)
        return result
    _s, _t, score_dict, _sm, _fb, _fbe, _it, _ot, _tw = out
    score_dict = {int(k): v for k, v in score_dict.items()}
    result["fresh_weights"] = score_dict

    order = sorted(score_dict, key=lambda k: -score_dict[k])
    chosen = None
    for i in order:
        if i in vetoed:
            continue
        chosen = i
        break
    if chosen is None:
        result["T_answer"] = None
        result["note"] = "all_top_chains_vetoed"
    else:
        result["T_answer"] = initial_answers.get(chosen)
        result["chosen_node"] = chosen
        result["chosen_model"] = unique_names[chosen]
        result["note"] = "top_passing_chain"
    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{idx}] done {result['time_s']}s | gold={gold} stored_A={result['stored_A']} "
          f"T={result.get('T_answer')} top=M{order[0]}({unique_names[order[0]]}) veto={vetoed}", flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--full_results", default="outputs/hard_full_198.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    with open(args.data_path) as f:
        samples = json.load(f)
    qmap = {i: s["question"] for i, s in enumerate(samples)}
    with open(args.full_results) as f:
        records = json.load(f)
    for r in records:
        r["question"] = qmap.get(r["idx"], "")
    recs = [r for r in records if r["idx"] in CAT22]
    print(f"[Top22] questions: {len(recs)}", flush=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, rec): rec["idx"] for rec in recs}
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
            print(f"[Top22] progress {done}/{len(recs)}", flush=True)
    print(f"[Top22] saved {len(results)} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
