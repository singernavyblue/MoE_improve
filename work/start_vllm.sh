#!/bin/bash
# Start 7 vLLM services on 6 GPUs (6 participant models + Prometheus judge).
# Packing: Prometheus alone on GPU0 (needs 8192 ctx); Saul+Mathstral share GPU3.
#   GPU0: prometheus 0.95 / 8192 / eager
#   GPU1: qwen 0.92 / 8192
#   GPU2: qwen_coder 0.92 / 4096
#   GPU3: mathstral 0.48 / 4096 / eager + saul 0.48 / 4096 / eager
#   GPU4: biomedical 0.92 / 4096
#   GPU5: finance 0.92 / 4096
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa

mkdir -p /root/vllm_logs

launch() {
  local gpu=$1 port=$2 model=$3 extra=$4 maxlen=$5 eager=$6
  CUDA_VISIBLE_DEVICES=$gpu nohup vllm serve "$model" \
    --port "$port" --max-model-len "${maxlen:-4096}" --gpu-memory-utilization "$extra" \
    ${eager:+--enforce-eager} \
    --served-model-name "$model" \
    > "/root/vllm_logs/${port}.log" 2>&1 < /dev/null &
  echo "launched $model on GPU$gpu port $port"
}

# GPUs 1-5: one participant model each
launch 1 8000 "Qwen/Qwen2.5-7B-Instruct" 0.92 8192
launch 2 8001 "Qwen/Qwen2.5-Coder-7B-Instruct" 0.92 4096
launch 4 8003 "BioMistral/BioMistral-7B" 0.92 4096
launch 5 8004 "instruction-pretrain/finance-Llama3-8B" 0.92 4096
# GPU3: mathstral first, then saul (both eager, 0.48 each)
launch 3 8002 "mistralai/Mathstral-7B-v0.1" 0.48 4096 eager
# Prometheus alone on GPU0 with 8192 context
CUDA_VISIBLE_DEVICES=0 nohup vllm serve "prometheus-eval/prometheus-7b-v2.0" \
  --port 8006 --max-model-len 8192 --gpu-memory-utilization 0.95 --enforce-eager \
  --served-model-name "prometheus-eval/prometheus-7b-v2.0" \
  > "/root/vllm_logs/8006.log" 2>&1 < /dev/null &
echo "launched prometheus-eval/prometheus-7b-v2.0 on GPU0 port 8006"

# Saul on GPU3 after mathstral has reserved its pool
sleep 45
launch 3 8005 "Equall/Saul-7B-Instruct-v1" 0.48 4096 eager

echo "ALL_LAUNCHED"

echo "ALL_LAUNCHED"
