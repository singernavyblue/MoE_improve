#!/usr/bin/env bash
# Frozen cross-benchmark evaluation for the conflict-localized MCQ QAE variant.
set -euo pipefail

GOA_DIR=${GOA_DIR:-/root/GoA}
PYTHON=${PYTHON:-/root/autodl-tmp/goa/bin/python}
VLLM=${VLLM:-/root/autodl-tmp/goa/bin/vllm}
PORT=${PORT:-8000}
QWEN_MODEL=${QWEN_MODEL:-/root/autodl-tmp/hf/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28}
MATHSTRAL_MODEL=${MATHSTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--mistralai--Mathstral-7B-v0.1/snapshots/ec3a48484ef241dfe03282edcb0f25e564923823}
BIOMISTRAL_MODEL=${BIOMISTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--BioMistral--BioMistral-7B/snapshots/9a11e1ffa817c211cbb52ee1fb312dc6b61b40a5}

export HF_HOME=${HF_HOME:-/root/autodl-tmp/hf}
export HF_HUB_OFFLINE=1
cd "$GOA_DIR"

stop_server() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" || true; wait "$SERVER_PID" || true; fi
  SERVER_PID=""
  for _ in $(seq 1 30); do curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 || return 0; sleep 1; done
  echo "port ${PORT} remained occupied after vLLM shutdown" >&2; exit 1
}
trap stop_server EXIT
start_server() {
  stop_server
  CUDA_VISIBLE_DEVICES=0 "$VLLM" serve "$1" --port "$PORT" --max-model-len 8192 --gpu-memory-utilization 0.90 --enforce-eager --served-model-name "$2" > "/root/vllm_logs/qae_localized_cross_${PORT}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 && return; sleep 2; done
  tail -100 "/root/vllm_logs/qae_localized_cross_${PORT}.log"; exit 1
}
run_one() {
  local ds="$1" source="outputs/qae_${1}_source.json" out="outputs/qae_localized_${1}.json" summary="outputs/qae_localized_${1}_summary.json"
  run() { "$PYTHON" run_qae_localized.py --stage "$1" --model "$2" --source "$source" --out "$out" --summary "$summary" --limit 0; }
  run hard qwen
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  run claims qwen
  run localize qwen
  for spec in "qwen:$QWEN_MODEL:Qwen/Qwen2.5-7B-Instruct" "mathstral:$MATHSTRAL_MODEL:mistralai/Mathstral-7B-v0.1" "biomedical_llama:$BIOMISTRAL_MODEL:BioMistral/BioMistral-7B"; do
    IFS=: read -r key model served <<< "$spec"; start_server "$model" "$served"; run verify "$key"
  done
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  for stage in ledger guard clean rebuttal pool summary; do run "$stage" qwen; done
}

run_one medmcqa
run_one mmlu
run_one mmlu_pro
