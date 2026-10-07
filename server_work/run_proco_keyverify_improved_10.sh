#!/usr/bin/env bash
# Run the stricter 10-item ProCo validation, with one model resident at a time.
set -euo pipefail

GOA_DIR=${GOA_DIR:-/root/GoA}
PYTHON=${PYTHON:-/root/autodl-tmp/goa/bin/python}
VLLM=${VLLM:-/root/autodl-tmp/goa/bin/vllm}
PORT=${PORT:-8000}
OUT=${OUT:-outputs/proco_keyverify_improved_10.json}
SUMMARY=${SUMMARY:-outputs/proco_keyverify_improved_10_summary.json}
LIMIT=${LIMIT:-10}
QWEN_MODEL=${QWEN_MODEL:-/root/autodl-tmp/hf/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28}
MATHSTRAL_MODEL=${MATHSTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--mistralai--Mathstral-7B-v0.1/snapshots/ec3a48484ef241dfe03282edcb0f25e564923823}
BIOMISTRAL_MODEL=${BIOMISTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--BioMistral--BioMistral-7B/snapshots/9a11e1ffa817c211cbb52ee1fb312dc6b61b40a5}
PROMETHEUS_MODEL=${PROMETHEUS_MODEL:-/root/autodl-tmp/hf/hub/models--prometheus-eval--prometheus-7b-v2.0/snapshots/66ffb1fc20beebfb60a3964a957d9011723116c5}

export HF_HOME=${HF_HOME:-/root/autodl-tmp/hf}
export HF_HUB_OFFLINE=1
cd "$GOA_DIR"

stop_server() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" || true
    wait "$SERVER_PID" || true
  fi
  SERVER_PID=""
}
trap stop_server EXIT

start_server() {
  local model="$1" max_len="$2" served_name="$3"
  stop_server
  CUDA_VISIBLE_DEVICES=0 "$VLLM" serve "$model" --port "$PORT" \
    --max-model-len "$max_len" --gpu-memory-utilization 0.90 --enforce-eager \
    --served-model-name "$served_name" > "/root/vllm_logs/proco_improved_${PORT}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do
    if curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done
  tail -100 "/root/vllm_logs/proco_improved_${PORT}.log" || true
  echo "vLLM did not become ready for ${model}" >&2
  exit 1
}

run_verifier() {
  local key="$1" model="$2" served_name="$3"
  start_server "$model" 6144 "$served_name"
  "$PYTHON" run_proco_keyverify_improved.py --stage verifier --model "$key" --out "$OUT" --summary "$SUMMARY" --limit "$LIMIT"
}

run_verifier qwen "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
run_verifier mathstral "$MATHSTRAL_MODEL" mistralai/Mathstral-7B-v0.1
run_verifier biomedical_llama "$BIOMISTRAL_MODEL" BioMistral/BioMistral-7B

start_server "$PROMETHEUS_MODEL" 8192 prometheus-eval/prometheus-7b-v2.0
"$PYTHON" run_proco_keyverify_improved.py --stage judge --out "$OUT" --summary "$SUMMARY" --limit "$LIMIT"
"$PYTHON" run_proco_keyverify_improved.py --stage summary --out "$OUT" --summary "$SUMMARY" --limit "$LIMIT"
