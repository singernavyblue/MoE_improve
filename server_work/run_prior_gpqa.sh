#!/bin/bash
# Controlled experiment: ability-profile prior blended into pairwise-margin scores.
# score(m) = w1 * prior(m, question_primary_dim) + (1-w1) * pairwise_margin(m)
# w1=0.1 calibrated on the 40-question set (15/40 -> 17/40 chain selection).
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

python main.py --data GPQA --eval test --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul --meta_llm qwen --graph_pooling_method mean --top_k 3 --threshold 0.05 --rounds 1 --temperature 0.7 --max_tokens 800 --num_proc 80 --seed 0 --edge_mode pairwise_margin_prior --prior_w1 0.1 --profile_path /root/prior_accuracy.json --dim_map_path /root/test_dim_map.json 2>&1 | tee /root/goa_prior.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "PRIOR_DONE"
