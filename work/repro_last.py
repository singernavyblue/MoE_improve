#!/usr/bin/env python
"""Reproduce the failure on the last GPQA question (idx 197)."""
import json
import os
import sys
import traceback

os.environ.setdefault("HF_HOME", "/root/autodl-tmp/hf")
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, "/root/GoA")

from main import process_fn


def main():
    samples = json.load(open("/root/GoA/data/test/GPQA_test.json"))
    item = dict(samples[-1])
    item["instruction"] = (
        f"Question: {item['question']}\n"
        f"Provide your step-by-step reasoning first, and then print \"The answer is (x)\", "
        f"where x is the answer choice (one capital letter), at the end of your response."
    )
    final_prompt = (
        f"Please conclude by printing \"The answer is (x)\", where x is the answer choice "
        f"(one capital letter), at the end of your response."
    )
    try:
        r = process_fn(
            item=item,
            data="GPQA",
            reference_models=["qwen", "qwen_coder", "mathstral", "biomedical_llama", "finance_llama", "saul"],
            temperature=0.7,
            max_tokens=800,
            rounds=1,
            top_k=3,
            threshold=0.05,
            meta_llm="qwen",
            graph_pooling_method="mean",
            output_path="/tmp/repro_out.json",
            num_choice=4,
            final_prompt=final_prompt,
            seed=0,
        )
        print("RESULT_OK:", r)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
