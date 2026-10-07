#!/usr/bin/env bash
# Frozen MATH (100) and HumanEval (50) localized free-response QAE evaluation.
set -euo pipefail
GOA_DIR=${GOA_DIR:-/root/GoA}
ORIG_DIR=${ORIG_DIR:-/root/GoA_orig}
PYTHON=${PYTHON:-/root/autodl-tmp/goa/bin/python}
VLLM=${VLLM:-/root/autodl-tmp/goa/bin/vllm}
PORT=${PORT:-8000}
QWEN_MODEL=${QWEN_MODEL:-/root/autodl-tmp/hf/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28}
MATHSTRAL_MODEL=${MATHSTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--mistralai--Mathstral-7B-v0.1/snapshots/ec3a48484ef241dfe03282edcb0f25e564923823}
BIOMISTRAL_MODEL=${BIOMISTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--BioMistral--BioMistral-7B/snapshots/9a11e1ffa817c211cbb52ee1fb312dc6b61b40a5}
export HF_HOME=${HF_HOME:-/root/autodl-tmp/hf} HF_HUB_OFFLINE=1
cd "$GOA_DIR"
stop_server() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" || true; wait "$SERVER_PID" || true; fi
  SERVER_PID=""
  for _ in $(seq 1 30); do curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 || return 0; sleep 1; done
  exit 1
}
trap stop_server EXIT
start_server() {
  stop_server
  CUDA_VISIBLE_DEVICES=0 "$VLLM" serve "$1" --port "$PORT" --max-model-len 8192 --gpu-memory-utilization 0.90 --enforce-eager --served-model-name "$2" > "/root/vllm_logs/qae_localized_free_${PORT}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 && return; sleep 2; done
  tail -100 "/root/vllm_logs/qae_localized_free_${PORT}.log"; exit 1
}
run_dataset() {
  local ds="$1" mode="$2" paired="$3" data="$4" out="outputs/qae_localized_${1}_free.json" summary="outputs/qae_localized_${1}_free_summary.json"
  run() { "$PYTHON" run_qae_localized_free.py --stage "$1" --dataset "$ds" --mode "$mode" --paired "$paired" --data "$data" --out "$out" --summary "$summary" --limit 0 --model "$2"; }
  run hard qwen
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  run claims qwen; run localize qwen
  for spec in "qwen:$QWEN_MODEL:Qwen/Qwen2.5-7B-Instruct" "mathstral:$MATHSTRAL_MODEL:mistralai/Mathstral-7B-v0.1" "biomedical_llama:$BIOMISTRAL_MODEL:BioMistral/BioMistral-7B"; do
    IFS=: read -r key model served <<< "$spec"; start_server "$model" "$served"; run verify "$key"
  done
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  for stage in ledger guard clean rebuttal candidate_hard pool summary; do run "$stage" qwen; done
}
run_dataset math math "$ORIG_DIR/outputs/paired_math_Aquick.json" "$ORIG_DIR/data/test/MATH_test.json"
run_dataset humaneval code "$ORIG_DIR/outputs/paired_humaneval_Aquick.json" "$ORIG_DIR/data/dev/human_eval_dev.json"
