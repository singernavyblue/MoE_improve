#!/usr/bin/env python3
"""Compare ablation runs vs pairwise-margin baseline on GPQA test (198)."""
import json, glob, os, sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
NAME = "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin"

def load(path):
    with open(path) as f:
        return json.load(f)

def acc(data):
    return sum(1 for d in data if d["answer"] == d["gold_answer"]) / len(data) * 100

def get(path):
    if not os.path.exists(path):
        return None
    return {d["idx"]: d for d in load(path)}

baseline = get(os.path.join(OUT, NAME + ".json"))
if baseline is None:
    print("BASELINE NOT FOUND", os.path.join(OUT, NAME + ".json"))
    sys.exit(1)

variants = {
    "A_anti_syc": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_anti_syc.json",
    "B_div": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_div.json",
    "C_both": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_anti_syc_div.json",
    "D_vote": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_vote.json",
    "E_exp": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_exp.json",
    "F_trust_r2": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_2_seed_0_judge_nogold_pairwise_margin_trust_r2.json",
    "G_trust_r2_exp": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_2_seed_0_judge_nogold_pairwise_margin_trust_r2_exp.json",
    "H1_topk6": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_6_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin.json",
    "J1_judge_qwen": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_judge_qwen.json",
    "J2_judge_mathstral": "goa_r_qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul_m_qwen_pooling_mean_top_k_3_t_0.05_n_1_seed_0_judge_nogold_pairwise_margin_judge_mathstral.json",
}

print(f"Baseline margin: {acc(list(baseline.values())):.2f}% ({sum(1 for d in baseline.values() if d['answer']==d['gold_answer'])}/198)")

for tag, fname in variants.items():
    data = get(os.path.join(OUT, fname))
    if data is None:
        print(f"[{tag}] NOT FOUND: {fname}")
        continue
    a = acc(list(data.values()))
    base = list(baseline.values())
    both = [d for d in data.values() if d["idx"] in baseline]
    base_map = {d["idx"]: d for d in base}
    strict = [d for d in both if base_map[d["idx"]]["sampled_nodes"] == d["sampled_nodes"]]
    sa = sum(1 for d in strict if d["answer"] == d["gold_answer"]) / len(strict) * 100 if strict else 0
    flip_ok = sum(1 for d in strict if base_map[d["idx"]]["answer"] != d["gold_answer"] and d["answer"] == d["gold_answer"])
    flip_bad = sum(1 for d in strict if base_map[d["idx"]]["answer"] == d["gold_answer"] and d["answer"] != d["gold_answer"])
    both_wrong = sum(1 for d in strict if base_map[d["idx"]]["answer"] != d["gold_answer"] and d["answer"] != d["gold_answer"])
    both_ok = sum(1 for d in strict if base_map[d["idx"]]["answer"] == d["gold_answer"] and d["answer"] == d["gold_answer"])
    print(f"[{tag}] acc={a:.2f}% ({sum(1 for d in data.values() if d['answer']==d['gold_answer'])}/198) | strict n={len(strict)} acc={sa:.2f}% | flips vs base: 转对{flip_ok} 转错{flip_bad} 都错{both_wrong} 都对{both_ok}")
    for idx in [1, 10, 27]:
        if idx in data and idx in baseline:
            d, b = data[idx], base_map[idx]
            print(f"    idx={idx} gold={d['gold_answer']} base={b['answer']} {tag}={d['answer']}")
