# -*- coding: utf-8 -*-
"""
Baseline A with the THIRD-PARTY judge swapped to DeepSeek (control variable:
answering side unchanged, frozen 3x7B initial chains, same GoA pipeline body).

Per question, matched against the stored Prometheus-judge baseline A from
outputs/hard_full_198.json:
  A       = stored baseline (Prometheus pairwise_margin + 1-round message passing
            + qwen weighted-mean pooling), 67/198
  A_ds    = identical pipeline, only edge_sampling's pairwise_margin judge is
            deepseek-chat (API); message passing / meta pooling / frozen chains
            are untouched.

The run reports fixed / broken / same and the exact two-sided McNemar p-value.
"""

import json
import os
import time
import math
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed

from teacher_validation import (
    make_instruction,
    _extract_letter,
    _sanitize,
)
from run_hard_weak import _rebuild, _run_baseline_like


def _mcnemar_exact_p(b, c):
    """Exact two-sided McNemar p on discordant counts (fixed=b, broken=c)."""
    n = b + c
    if n == 0:
        return 1.0
    # P(X <= min(b,c)) under Bin(n, 0.5), doubled (clamped at 1).
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * p)


def run_one(item, initials_by_idx, judge_label="ds", judge_model="deepseek",
            edge_mode="pairwise_margin"):
    cfg = _rebuild(item, initials_by_idx)
    rec = initials_by_idx[item["idx"]]
    stored_A = ((rec.get("A") or {}).get("answer") if isinstance(rec, dict) else None)
    result = {
        "idx": cfg["idx"], "gold": cfg["gold"],
        "sampled_nodes": cfg["sampled_nodes"], "unique_names": cfg["unique_names"],
        "initial_answers": cfg["initial_answers"],
        "stored_A": stored_A,
    }
    t0 = time.time()
    try:
        fa, score_a, note_a, _ = _run_baseline_like(
            cfg["models_dict_unique"], cfg["model_name_idx"], cfg["initial_responses"],
            cfg["instruction"], scale=None, judge_model=judge_model, edge_mode=edge_mode,
        )
        result[f"A_{judge_label}"] = _extract_letter(fa)
        result["final_response"] = fa
        result["pool_note"] = note_a
        result["score_dict"] = score_a
    except Exception as e:
        result[f"A_{judge_label}"] = None
        result["error"] = str(e)
        print(f"[{cfg['idx']}] error: {e}", flush=True)
    result["time_s"] = round(time.time() - t0, 1)
    print(f"[{cfg['idx']}] done {result['time_s']}s | gold={cfg['gold']} "
          f"A={stored_A} A_{judge_label}={result.get(f'A_{judge_label}')} "
          f"note={result.get('pool_note')}",
          flush=True)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data_path", default="data/test/GPQA_test.json")
    ap.add_argument("--initials_path", default="outputs/hard_full_198.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--judge", choices=["deepseek", "prometheus"], default="deepseek")
    ap.add_argument("--edge_mode", choices=["pairwise_margin", "pairwise_margin_4dim"],
                    default="pairwise_margin")
    args = ap.parse_args()
    judge_label = "ds" if args.judge == "deepseek" else "prom"
    judge_model = args.judge
    if args.judge == "prometheus":
        judge_model = None  # default Prometheus path in edge_sampling

    with open(args.data_path) as f:
        samples = json.load(f)
    with open(args.initials_path) as f:
        old_results = json.load(f)
    initials_by_idx = {r["idx"]: r for r in old_results}

    items = [dict(s, idx=i) for i, s in enumerate(samples)]
    if args.limit:
        items = items[:args.limit]
    print(f"[DsJudgeBaseline] questions: {len(items)}", flush=True)
    assert "DEEPSEEK_API_KEY" in os.environ, "DEEPSEEK_API_KEY must be exported"

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, item, initials_by_idx,
                          judge_label, judge_model, args.edge_mode): item["idx"]
                for item in items}
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
            print(f"[DsJudgeBaseline] progress {done}/{len(items)}", flush=True)

    results.sort(key=lambda r: r["idx"])
    with open(args.out, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    a_correct = sum(1 for r in results if r.get("stored_A") == r["gold"])
    jkey = f"A_{judge_label}"
    j_correct = sum(1 for r in results if r.get(jkey) == r["gold"])
    fixed = sum(1 for r in results
                if r.get("stored_A") != r["gold"] and r.get(jkey) == r["gold"])
    broken = sum(1 for r in results
                 if r.get("stored_A") == r["gold"] and r.get(jkey) != r["gold"])
    p = _mcnemar_exact_p(fixed, broken)
    print("=" * 60, flush=True)
    print(f"[DsJudgeBaseline] n={len(results)} "
          f"A={a_correct} ({a_correct / max(len(results), 1):.2%}) | "
          f"A_{judge_label}({args.judge} judge)={j_correct} "
          f"({j_correct / max(len(results), 1):.2%})",
          flush=True)
    print(f"[DsJudgeBaseline] fixed={fixed} broken={broken} "
          f"same={len(results) - fixed - broken} McNemar p={p:.4g}", flush=True)
    print(f"[DsJudgeBaseline] saved {len(results)} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
