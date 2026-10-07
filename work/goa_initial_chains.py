# -*- coding: utf-8 -*-
"""Generate initial responses (node sampling + first answers) for a fixed set of GPQA idxs.
Run on the server inside /root/GoA. Saves initial chains for judge-ablation comparison.
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from collections import Counter

sys.path.insert(0, "/root/GoA")
from endpoint import model_endpoint_dict
from modules import (
    node_sampling_model_card,
    generate_initial_response_with_confidence,
    maybe_replace_with_general,
)

REF_MODELS = ["qwen", "qwen_coder", "mathstral", "biomedical_llama", "finance_llama", "saul"]
TOP_K = 3
TEMP = 0.7
MAX_TOKENS = 800
SEED = 0
NUM_CHOICE = 4


def make_unique_node_names(sampled_nodes):
    counts = Counter(sampled_nodes)
    seen = {}
    unique_names = []
    unique_to_original = {}
    for name in sampled_nodes:
        if counts[name] > 1:
            idx = seen.get(name, 0)
            unique_name = f"{name}_{idx}"
            seen[name] = idx + 1
        else:
            unique_name = name
        unique_names.append(unique_name)
        unique_to_original[unique_name] = name
    return unique_names, unique_to_original


def make_instruction(sample):
    return (
        f"Question: {sample['question']}\n"
        f"Provide your step-by-step reasoning first, and then print \"The answer is (x)\", "
        f"where x is the answer choice (one capital letter), at the end of your response."
    )


def _worker(args):
    idx, samples, id2pos = args
    return process(idx, samples, id2pos)


def process(idx, samples, id2pos):
    sample = samples[id2pos[str(idx)]]
    instruction = make_instruction(sample)
    meta = model_endpoint_dict["qwen"]
    models_dict = {k: v for k, v in model_endpoint_dict.items() if k in REF_MODELS}

    sampled_nodes, fallback, *_ = node_sampling_model_card(
        model=meta["model_id"],
        endpoint=meta["url"],
        messages=[instruction],
        model_info_dict=models_dict,
        top_k=TOP_K,
        temperature=TEMP,
        max_tokens=MAX_TOKENS,
        seed=SEED,
    )
    unique_names, unique_to_original = make_unique_node_names(sampled_nodes)
    initial_responses, confidences, answers = {}, {}, {}

    for i, uname in enumerate(unique_names):
        orig = unique_to_original[uname]
        cfg = models_dict[orig]
        raw, ans, conf, *_ = generate_initial_response_with_confidence(
            model_id=cfg["model_id"],
            endpoint=cfg["url"],
            instruction=instruction,
            data="gpqa",
            num_choice=NUM_CHOICE,
            temperature=TEMP,
            max_tokens=MAX_TOKENS,
            seed=SEED,
            debug_txt=f"[Init-{uname}] ",
        )
        initial_responses[i] = raw
        confidences[i] = conf
        answers[i] = ans

    for i, uname in enumerate(list(unique_names)):
        orig = unique_to_original[uname]
        replaced, *_ = maybe_replace_with_general(
            node_idx=i,
            node_name=orig,
            confidence=confidences[i],
            models_dict=models_dict,
            general_model_name="qwen",
            initial_responses=initial_responses,
            confidences=confidences,
            answers=answers,
            sampled_nodes=sampled_nodes,
            instruction=instruction,
            data="gpqa",
            num_choice=NUM_CHOICE,
            temperature=TEMP,
            max_tokens=MAX_TOKENS,
            seed=SEED,
        )
        if replaced:
            unique_names[i] = "qwen" if unique_names.count("qwen") == 0 else f"qwen_{i}"
            unique_to_original[unique_names[i]] = "qwen"

    return {
        "idx": idx,
        "question": sample["question"],
        "gold": sample["gold_answer"],
        "instruction": instruction,
        "sampled_nodes": unique_names,
        "initial_responses": {str(k): v for k, v in initial_responses.items()},
        "answers": {str(k): v for k, v in answers.items()},
        "confidences": {str(k): float(v) for k, v in confidences.items()},
    }


def main():
    idxs = json.load(open("/root/GoA/judge_ablation_40_idxs.json"))
    samples = json.load(open("/root/GoA/data/test/GPQA_test.json"))
    id2pos = {str(s["idx"]): p for p, s in enumerate(samples)} if "idx" in samples[0] else {str(p): p for p in range(len(samples))}
    with ProcessPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_worker, [(idx, samples, id2pos) for idx in idxs]))
    out = "/root/GoA/outputs/judge_ablation_40_initial_chains.json"
    json.dump(results, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"SAVED {len(results)} chains to {out}")


if __name__ == "__main__":
    main()
