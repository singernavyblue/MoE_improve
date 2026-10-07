#!/bin/bash
# Ablation runs on GPQA test (198 q) vs pairwise-margin baseline (41.41%).
# A: measure 9 only (anti-sycophancy prompts)
# B: measure 5 only (divergence-aware edges)
# C: measures 9 + 5
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

COMMON="--data GPQA --eval test --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul --meta_llm qwen --graph_pooling_method mean --top_k 3 --threshold 0.05 --rounds 1 --temperature 0.7 --max_tokens 800 --num_proc 80 --seed 0 --edge_mode pairwise_margin"

echo "======== RUN A: anti_sycophancy only ========"
python main.py $COMMON --anti_sycophancy True 2>&1 | tee /root/goa_ablation_A_antisyc.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN B: divergence_edges only ========"
python main.py $COMMON --divergence_edges True --divergence_gamma 0.5 --divergence_topk 2 2>&1 | tee /root/goa_ablation_B_div.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN C: anti_sycophancy + divergence ========"
python main.py $COMMON --anti_sycophancy True --divergence_edges True --divergence_gamma 0.5 --divergence_topk 2 2>&1 | tee /root/goa_ablation_C_both.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "ABLATION_ALL_DONE"
