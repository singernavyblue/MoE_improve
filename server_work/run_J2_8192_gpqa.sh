#!/bin/bash
# J2 rerun: judge=mathstral with 8192 context (saul endpoint down; 7 saul-sampled questions to be excluded in analysis).
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

python main.py \
  --data GPQA --eval test \
  --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul \
  --meta_llm qwen --graph_pooling_method mean --top_k 3 --threshold 0.05 --rounds 1 \
  --temperature 0.7 --max_tokens 800 --num_proc 80 --seed 0 --edge_mode pairwise_margin \
  --judge_model mathstral 2>&1 | tee /root/goa_ablation_J2_8192.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "J2_8192_DONE"
