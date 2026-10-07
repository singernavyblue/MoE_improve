#!/bin/bash
# Batch 3: two bottleneck-targeted controls vs margin baseline (41.41%).
# H1: larger initial pool (top_k=6, all 6 models, Prometheus judge)
# J1: judge swap -> qwen (general 7B)
# J2: judge swap -> mathstral (math/science 7B)
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

COMMON="--data GPQA --eval test --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul --meta_llm qwen --graph_pooling_method mean --threshold 0.05 --rounds 1 --temperature 0.7 --max_tokens 800 --num_proc 80 --seed 0 --edge_mode pairwise_margin"

echo "======== RUN H1: top_k=6 (full pool) ========"
python main.py $COMMON --top_k 6 2>&1 | tee /root/goa_ablation_H1_topk6.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN J1: judge=qwen ========"
python main.py $COMMON --top_k 3 --judge_model qwen 2>&1 | tee /root/goa_ablation_J1_judge_qwen.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN J2: judge=mathstral ========"
python main.py $COMMON --top_k 3 --judge_model mathstral 2>&1 | tee /root/goa_ablation_J2_judge_mathstral.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "ABLATION3_ALL_DONE"
