#!/bin/bash
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_ENABLE_HF_TRANSFER=0
export PATH=/root/miniconda3/bin:$PATH

python -m pip install -q -U huggingface_hub

MODELS=(
  "Qwen/Qwen2.5-7B-Instruct"
  "Qwen/Qwen2.5-Coder-7B-Instruct"
  "mistralai/Mathstral-7B-v0.1"
  "BioMistral/BioMistral-7B"
  "instruction-pretrain/finance-Llama3-8B"
  "Equall/Saul-7B-Instruct-v1"
  "prometheus-eval/prometheus-7b-v2.0"
)

for m in "${MODELS[@]}"; do
  echo "===== downloading $m ====="
  HF_ENDPOINT=https://hf-mirror.com python -c "
from huggingface_hub import snapshot_download
import sys
snapshot_download('$m', cache_dir='/root/autodl-tmp/hf')
print('OK $m')
" || HF_ENDPOINT=https://huggingface.co python -c "
from huggingface_hub import snapshot_download
snapshot_download('$m', cache_dir='/root/autodl-tmp/hf')
print('OK $m')
"
done
echo "ALL_DONE"
