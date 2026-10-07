# -*- coding: utf-8 -*-
"""Diagnose why J < A_orig on MATH / HumanEval (paired A-quick runs).
Run from /root/GoA_orig with the goa conda env."""
import json
import os
import re
import sys
import subprocess
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import is_math_equiv, extract_human_eval_completion


def _eq(a, b):
    if a in (None, "", "N/A") or b in (None, ""):
        return False
    try:
        return bool(is_math_equiv(str(a), str(b)))
    except Exception:
        return str(a).strip() == str(b).strip()


def analyze_math():
    d = json.load(open("outputs/paired_math_Aquick.json"))
    broken = [r for r in d if r.get("A_correct") and not r.get("J_correct")]
    print(f"[MATH] total={len(d)} A_ok={sum(1 for r in d if r.get('A_correct'))} "
          f"J_ok={sum(1 for r in d if r.get('J_correct'))} broken(A right, J wrong)={len(broken)}")
    cat = Counter()
    rows = []
    for r in broken:
        gold = str(r["gold"])
        inits = r.get("initial_answers") or {}
        pool_ok = [k for k, v in inits.items() if _eq(v, gold)]
        jw = r.get("J_winner")
        jans = inits.get(str(jw)) if jw is not None else None
        picked_gold = _eq(jans, gold)
        if not pool_ok:
            cat["gold_not_in_initial_pool(A的讨论把它做对了)"] += 1
        elif not picked_gold:
            cat["pool里有正确链但J挑了错的"] += 1
        else:
            cat["other"] += 1
        rows.append((r["idx"], gold, r.get("A_answer"), r.get("J_answer"), inits, jw, pool_ok))
    print("[MATH] broken breakdown:", dict(cat))
    print("[MATH] examples:")
    for idx, gold, aans, jans, inits, jw, pool_ok in rows[:6]:
        print(f"  idx={idx} gold={gold} A_answer={aans!r} J_answer={jans!r} "
              f"J_winner=M{jw} inits={inits} 池内含正确链的节点={pool_ok}")
    # also: how often did A win via discussion where pool had no gold
    a_right_no_pool = [r for r in d if r.get("A_correct") and not any(
        _eq(v, r["gold"]) for v in (r.get("initial_answers") or {}).values())]
    print(f"[MATH] A_orig correct but NO correct chain in initial pool: {len(a_right_no_pool)}")


def check_he(problem, completion, timeout=8):
    if not completion:
        return False
    source = (problem["prompt"] + "\n" + completion + "\n\n" + problem["test"]
              + "\n" + f"check({problem['entry_point']})")
    try:
        p = subprocess.run([sys.executable, "-c", source], capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def analyze_humaneval():
    d = json.load(open("outputs/paired_humaneval_Aquick.json"))
    dev = {r["task_id"]: r for r in json.load(open("data/dev/human_eval_dev.json"))}
    broken = [r for r in d if r.get("A_pass") and not r.get("J_pass")]
    print(f"\n[HumanEval] total={len(d)} A_ok={sum(1 for r in d if r.get('A_pass'))} "
          f"J_ok={sum(1 for r in d if r.get('J_pass'))} broken={len(broken)}")
    cat = Counter()
    for r in broken:
        problem = dev[r["task_id"]] if isinstance(r.get("task_id"), str) else None
        if problem is None:
            # idx maps to dev order
            idx = r["idx"]
            task_id = list(dev.keys())[idx] if idx < len(dev) else None
            problem = dev.get(task_id)
        inits = r.get("initial_responses") or {}
        node_pass = {}
        for k, raw in inits.items():
            node_pass[k] = check_he(problem, extract_human_eval_completion(raw))
        jw = r.get("J_winner")
        cat["至少有一条初始补全能过" if any(node_pass.values()) else "三条初始补全都过不了"] += 1
        if any(node_pass.values()) and (jw is None or not node_pass.get(str(jw))):
            cat["有能过的初始补全但J选了不能过的"] += 1
        print(f"  idx={r['idx']} task={problem['task_id']} entry={problem['entry_point']} "
              f"node_pass={node_pass} J_winner=M{jw} J_pass={r.get('J_pass')}")
    print("[HumanEval] broken breakdown:", dict(cat))


if __name__ == "__main__":
    analyze_math()
    analyze_humaneval()
