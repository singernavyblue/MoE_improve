#!/bin/bash
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_ENABLE_HF_TRANSFER=0
export HF_HUB_DISABLE_XET=1
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
  ok=0
  for attempt in 1 2 3 4 5; do
    echo "===== [$m] attempt $attempt ====="
    HF_ENDPOINT=https://hf-mirror.com python -u -c "
from huggingface_hub import snapshot_download
snapshot_download('$m')
print('OK $m')
" && ok=1 && break
    sleep 5
  done
  if [ $ok -eq 1 ]; then
    echo "===== DONE $m ====="
  else
    echo "===== FAILED $m after 5 attempts ====="
  fi
done
echo "ALL_DONE"
