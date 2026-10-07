#!/usr/bin/env python
"""Smoke-test pairwise Copeland edge sampling on one GPQA question."""
import json
import os
import sys

os.environ.setdefault("HF_HOME", "/root/autodl-tmp/hf")
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, "/root/GoA")

from modules import edge_sampling  # noqa: E402

data = json.load(open("/root/GoA/data/test/GPQA_test.json"))
item = data[0]
instruction = (
    f"Question: {item['question']}\n"
    f"Provide your step-by-step reasoning first, and then print \"The answer is (x)\", "
    f"where x is the answer choice (one capital letter), at the end of your response."
)

# Three synthetic reasoning chains: response 0 is clearly the most complete.
responses = {
    0: (
        "I will reason step by step. The molecule contains a benzene ring, which "
        "contributes 6 carbons, plus a propenal chain with 3 carbons, giving 9 "
        "carbons total. The reaction with methylmagnesium bromide adds one carbon. "
        "No further carbons are added. Total 10 carbons. The answer is (C)."
    ),
    1: "The answer is (A).",
    2: (
        "Cinnamaldehyde has 8 carbons. The Grignard reagent adds one carbon, so the "
        "product has 9 carbons. Therefore the answer is (B)."
    ),
}

model_name_idx = {0: "qwen", 1: "qwen_coder", 2: "biomedical_llama"}
models_dict = {"qwen": {}, "qwen_coder": {}, "biomedical_llama": {}}

out = edge_sampling(
    models_dict=models_dict,
    model_name_idx=model_name_idx,
    initial_responses=responses,
    messages=[instruction],
    threshold=0.05,
    temperature=0.2,
    max_tokens=512,
    max_retries=3,
    seed=0,
    edge_mode="pairwise_copeland",
)

if not isinstance(out, tuple):
    print("edge_sampling returned (non-tuple):", out)
else:
    source_edges, target_edges, score_dict, score_matrix, fallback_used, fallback_global, i_t_c, o_t_c = out
    print("=== score_dict:", score_dict)
    print("=== source_edges:", source_edges)
    print("=== target_edges:", target_edges)
    print("=== score_matrix:\n", score_matrix)
    print("=== fallback_used:", fallback_used)
