#!/bin/bash
# Re-run GPQA test (198 questions) with judge-based edge sampling.
# Same config as the original 6-model run, only edge scoring source changed.
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

python main.py \
  --data GPQA \
  --eval test \
  --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul \
  --meta_llm qwen \
  --graph_pooling_method mean \
  --top_k 3 \
  --threshold 0.05 \
  --rounds 1 \
  --temperature 0.7 \
  --max_tokens 800 \
  --num_proc 80 \
  --seed 0

echo "RUN_DONE"
