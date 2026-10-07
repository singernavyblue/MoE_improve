#!/bin/bash
# Batch 2 ablations vs pairwise-margin baseline (41.41%).
# D: measure 7 only (trust-weighted voting pooling)
# E: measure 2 only (exp/softmax weighting in mean pooling)
# F: measure 1 only (asymmetric trust update, R=2)
# G: measures 1+2 (asymmetric trust R=2 + exp weighting)
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

COMMON="--data GPQA --eval test --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul --meta_llm qwen --graph_pooling_method mean --top_k 3 --threshold 0.05 --temperature 0.7 --max_tokens 800 --num_proc 80 --seed 0 --edge_mode pairwise_margin"

echo "======== RUN D: voting_pooling only ========"
python main.py $COMMON --rounds 1 --voting_pooling True 2>&1 | tee /root/goa_ablation_D_vote.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN E: exp_pooling only ========"
python main.py $COMMON --rounds 1 --exp_pooling True 2>&1 | tee /root/goa_ablation_E_exp.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN F: trust_update R=2 only ========"
python main.py $COMMON --rounds 2 --trust_update True 2>&1 | tee /root/goa_ablation_F_trust_r2.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "======== RUN G: trust_update R=2 + exp_pooling ========"
python main.py $COMMON --rounds 2 --trust_update True --exp_pooling True 2>&1 | tee /root/goa_ablation_G_trust_exp.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "ABLATION2_ALL_DONE"
