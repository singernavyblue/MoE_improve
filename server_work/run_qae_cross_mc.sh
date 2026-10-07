#!/usr/bin/env bash
# QAE-Pooling + HARD on frozen MCQ subsets.
set -euo pipefail

GOA_DIR=${GOA_DIR:-/root/GoA}
PYTHON=${PYTHON:-/root/autodl-tmp/goa/bin/python}
QAE=${QAE:-$GOA_DIR/run_qae_pooling.py}
BUILDER=${BUILDER:-$GOA_DIR/build_qae_mc_source.py}
ORIG_DIR=${ORIG_DIR:-/root/GoA_orig}

run_one() {
  local ds="$1" data="$2" paired="$3"
  local source="outputs/qae_${ds}_source.json"
  local out="outputs/qae_${ds}_hard.json"
  local summary="outputs/qae_${ds}_hard_summary.json"
  "$PYTHON" "$BUILDER" --dataset "$ds" --data "$data" --paired "$paired" --out "$source"
  # The full QAE launcher supplies model paths and server lifecycle; this loop
  # invokes each stage so it can resume from its incrementally saved ledger.
  "$PYTHON" "$QAE" --stage hard --model qwen --source "$source" --out "$out" --summary "$summary" --limit 0
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  "$PYTHON" "$QAE" --stage plan --model qwen --source "$source" --out "$out" --summary "$summary" --limit 0
  for spec in "qwen:$QWEN_MODEL:Qwen/Qwen2.5-7B-Instruct" "mathstral:$MATHSTRAL_MODEL:mistralai/Mathstral-7B-v0.1" "biomedical_llama:$BIOMISTRAL_MODEL:BioMistral/BioMistral-7B"; do
    IFS=: read -r key model served <<< "$spec"
    start_server "$model" "$served"
    "$PYTHON" "$QAE" --stage verify --model "$key" --source "$source" --out "$out" --summary "$summary" --limit 0
  done
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  for stage in ledger clean rebuttal pool summary; do
    "$PYTHON" "$QAE" --stage "$stage" --model qwen --source "$source" --out "$out" --summary "$summary" --limit 0
  done
}

stop_server() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" || true; wait "$SERVER_PID" || true; fi
  SERVER_PID=""
  for _ in $(seq 1 30); do curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 || return 0; sleep 1; done
  exit 1
}
start_server() {
  stop_server
  CUDA_VISIBLE_DEVICES=0 "$VLLM" serve "$1" --port "$PORT" --max-model-len 8192 --gpu-memory-utilization 0.90 --enforce-eager --served-model-name "$2" > "/root/vllm_logs/qae_cross_${PORT}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 && return; sleep 2; done
  tail -100 "/root/vllm_logs/qae_cross_${PORT}.log"; exit 1
}

PORT=${PORT:-8000}
VLLM=${VLLM:-/root/autodl-tmp/goa/bin/vllm}
QWEN_MODEL=${QWEN_MODEL:-/root/autodl-tmp/hf/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28}
MATHSTRAL_MODEL=${MATHSTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--mistralai--Mathstral-7B-v0.1/snapshots/ec3a48484ef241dfe03282edcb0f25e564923823}
BIOMISTRAL_MODEL=${BIOMISTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--BioMistral--BioMistral-7B/snapshots/9a11e1ffa817c211cbb52ee1fb312dc6b61b40a5}
export HF_HOME=${HF_HOME:-/root/autodl-tmp/hf} HF_HUB_OFFLINE=1
cd "$GOA_DIR"
trap stop_server EXIT
run_one medmcqa "$ORIG_DIR/data/test/MedMCQA_sampled_test.json" "$ORIG_DIR/outputs/paired_medmcqa_Aquick.json"
run_one mmlu "$ORIG_DIR/data/test/MMLU_sampled_test.json" "$ORIG_DIR/outputs/paired_mmlu_Aquick.json"
run_one mmlu_pro "$ORIG_DIR/data/test/MMLU_Pro_sampled_test.json" "$ORIG_DIR/outputs/paired_mmlu_pro_Aquick.json"
