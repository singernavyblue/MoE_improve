#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摸底运行：6 个模型 × 150 题，输出作答矩阵（服务器上运行）。

用法（在 /root/GoA 下）：
  conda activate goa && python run_entrance.py \
      --items ../摸底题集_150.json --out ../摸底作答矩阵.json
"""

import argparse
import hashlib
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from endpoint import model_endpoint_dict
from utils import generate_vllm


def build_prompt(question, options, seed):
    """随机打乱选项顺序（固定 seed 防位置偏差），返回 (prompt, gold_letter)。"""
    idx = list(range(4))
    rng = random.Random(seed)
    rng.shuffle(idx)
    letters = "ABCD"
    gold_letter = letters[idx.index(0)]  # 0 号选项即 correct
    lines = [question, "", "The options are:"]
    for pos, orig in enumerate(idx):
        lines.append(f"({letters[pos]}) {options[orig]}")
    return "\n".join(lines), gold_letter


def parse_letter(output):
    """从模型输出中提取选项字母 A-D。"""
    out = output or ""
    patterns = [
        r"(?:answer|Answer|ans|Ans)\s*(?:is|:)?\s*\(?([A-D])\)?",
        r"\\boxed\{\(([A-D])\)\}",
        r"\\boxed\{([A-D])\}",
        r"(?:option|Option)\s*\(?([A-D])\)?",
        r"\(([A-D])\)\s*$",
        r"\b([A-D])\b\s*[.。]?\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, out, flags=re.M)
        if m:
            return m.group(1)
    m = re.findall(r"\(([A-D])\)", out)
    return m[-1] if m else None


def run_one(model_key, cfg, item, idx):
    options = [item["correct"]] + item["incorrect"]
    seed = int(hashlib.sha1(item["record_id"].encode()).hexdigest()[:8], 16)
    prompt, gold = build_prompt(item["question"], options, seed)
    try:
        raw, _, _, _, _ = generate_vllm(
            model=cfg["model_id"],
            endpoint=cfg["url"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.7,
            debug_txt=f"[Entrance-{model_key}-{idx}]",
            seed=0,
        )
        letter = parse_letter(raw)
        return {
            "record_id": item["record_id"],
            "answer": letter,
            "correct": 1 if letter == gold else 0,
            "gold": gold,
            "raw": raw,
        }
    except Exception as e:
        print(f"[Entrance-{model_key}-{idx}] ERROR: {e}")
        return {"record_id": item["record_id"], "answer": None, "correct": 0, "gold": gold, "raw": ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True, help="摸底题集 JSON（selected 数组）")
    ap.add_argument("--out", required=True, help="输出作答矩阵 JSON")
    ap.add_argument("--models", default="qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    items = json.load(open(args.items, encoding="utf-8"))["selected"]
    models = [m for m in args.models.split(",") if m in model_endpoint_dict]
    print(f"models: {models} | items: {len(items)}")

    results = {m: {} for m in models}
    for mkey in models:
        cfg = model_endpoint_dict[mkey]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(run_one, mkey, cfg, it, i): (i, it) for i, it in enumerate(items)}
            for fu in as_completed(futs):
                rec = fu.result()
                results[mkey][rec["record_id"]] = rec

    out = {"models": models, "n_items": len(items), "results": results}
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for mkey in models:
        n = len(results[mkey])
        acc = sum(1 for r in results[mkey].values() if r["correct"]) / max(n, 1)
        print(f"{mkey}: {n} 题，正确率 {acc:.1%}")
    print("saved:", args.out)


if __name__ == "__main__":
    main()
