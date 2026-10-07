# -*- coding: utf-8 -*-
"""Analyze teacher-script validation results (conditions A/B/C on the 40-question subset)."""

import json
import sys
from collections import Counter


def load(path):
    with open(path) as f:
        return json.load(f)


def mcnemar(a_correct, b_correct, a_wrong_b_correct, a_correct_b_wrong):
    """Exact McNemar test p-value (two-sided) for paired binary outcomes."""
    b = a_wrong_b_correct
    c = a_correct_b_wrong
    n = b + c
    if n == 0:
        return 1.0
    # two-sided exact binomial
    from math import comb
    p = 0.0
    for k in range(0, min(b, c) + 1):
        p += comb(n, k) * (0.5 ** n)
    p *= 2
    return min(1.0, p)


def main(path):
    data = load(path)
    print(f"questions: {len(data)}")

    acc = {}
    flips = {}
    for cond in ["A", "B", "C"]:
        correct = sum(1 for r in data if r.get(cond, {}).get("answer") == r["gold"])
        acc[cond] = correct
        if cond != "A":
            w2c = sum(1 for r in data
                      if r["A"].get("answer") != r["gold"] and r.get(cond, {}).get("answer") == r["gold"])
            c2w = sum(1 for r in data
                      if r["A"].get("answer") == r["gold"] and r.get(cond, {}).get("answer") != r["gold"])
            flips[cond] = (w2c, c2w)

    n = len(data)
    print("\n== Accuracy ==")
    for cond in ["A", "B", "C"]:
        print(f"{cond}: {acc[cond]}/{n} = {acc[cond]/n*100:.2f}%")

    print("\n== Flips vs A (转对, 转错) ==")
    for cond in ["B", "C"]:
        w2c, c2w = flips[cond]
        print(f"{cond}: 转对 {w2c} / 转错 {c2w}")

    print("\n== McNemar (vs A) ==")
    for cond in ["B", "C"]:
        w2c, c2w = flips[cond]
        p = mcnemar(acc["A"], acc[cond], w2c, c2w)
        print(f"{cond} vs A: p = {p:.4f}")

    print("\n== Bad cases ==")
    for r in data:
        if r["idx"] in (1, 10, 27):
            print(f"idx {r['idx']}: gold={r['gold']} "
                  f"A={r.get('A', {}).get('answer')} B={r.get('B', {}).get('answer')} "
                  f"C={r.get('C', {}).get('answer')}")

    print("\n== Convergence distribution (condition B) ==")
    convs = Counter()
    for r in data:
        c = r.get("B", {}).get("convergence")
        if isinstance(c, dict):
            convs[c.get("convergence", "unparsed")] += 1
        else:
            convs["no_convergence_check"] += 1
    for k, v in convs.items():
        print(f"  {k}: {v}")

    # Transactivity compliance (B round1): did revision reference the partner chain?
    print("\n== Transactivity (B) ==")
    trans_count = 0
    for r in data:
        meta = r.get("B", {}).get("round1_meta") or {}
        for i, m in meta.items():
            if m.get("partner") is not None:
                trans_count += 1
    print(f"  transactive revisions issued: {trans_count}")

    # Errors
    print("\n== Errors ==")
    for r in data:
        for cond in ["A", "B", "C"]:
            if "error" in r.get(cond, {}):
                print(f"  idx {r['idx']} {cond}: {r[cond]['error'][:120]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "outputs/teacher_val_40.json")
