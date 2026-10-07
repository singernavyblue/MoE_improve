#!/usr/bin/env python
"""Reproduce the UnboundLocalError in the original GoA code."""
import json
import os
import sys
import traceback

os.environ.setdefault("HF_HOME", "/root/autodl-tmp/hf")
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, "/root/GoA_orig")

from main import _process_fn_impl


def main():
    samples = json.load(open("/root/GoA_orig/data/test/GPQA_test.json"))
    for idx in [3, 5, 75]:
        item = dict(samples[idx])
        item["instruction"] = (
            f"Question: {item['question']}\n"
            f"Provide your step-by-step reasoning first, and then print \"The answer is (x)\", "
            f"where x is the answer choice (one capital letter), at the end of your response."
        )
        item["idx"] = idx
        final_prompt = (
            f"Please conclude by printing \"The answer is (x)\", where x is the answer choice "
            f"(one capital letter), at the end of your response."
        )
        print(f"===== idx {idx} =====")
        try:
            r = _process_fn_impl(
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
                output_path="/tmp/repro_orig_out.json",
                num_choice=4,
                final_prompt=final_prompt,
                seed=0,
            )
            print("RESULT:", r.get("answer"), r.get("sampled_nodes"))
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
