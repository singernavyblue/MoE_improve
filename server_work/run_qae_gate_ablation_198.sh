#!/usr/bin/env bash
# Fixed-source GPQA ablation: comparison slots/exact spans are held constant;
# the three requested gates are enabled cumulatively across four runs.
set -euo pipefail

GOA_DIR=${GOA_DIR:-/root/GoA}
PYTHON=${PYTHON:-/root/autodl-tmp/goa/bin/python}
VLLM=${VLLM:-/root/autodl-tmp/goa/bin/vllm}
PORT=${PORT:-8000}
SOURCE=${SOURCE:-outputs/qae_pooling_full_source_hard_v2.json}
PREFIX=${PREFIX:-outputs/qae_gate_ablation_198_20261007}
SEED_OUT=${SEED_OUT:-${PREFIX}_shared_claims.json}
SEED_SUMMARY=${SEED_SUMMARY:-${PREFIX}_shared_claims_summary.json}
QWEN_MODEL=${QWEN_MODEL:-/root/autodl-tmp/hf/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28}
MATHSTRAL_MODEL=${MATHSTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--mistralai--Mathstral-7B-v0.1/snapshots/ec3a48484ef241dfe03282edcb0f25e564923823}
BIOMISTRAL_MODEL=${BIOMISTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--BioMistral--BioMistral-7B/snapshots/9a11e1ffa817c211cbb52ee1fb312dc6b61b40a5}

export HF_HOME=${HF_HOME:-/root/autodl-tmp/hf}
export HF_HUB_OFFLINE=1
cd "$GOA_DIR"
mkdir -p /root/vllm_logs

stop_server() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" || true
    wait "$SERVER_PID" || true
  fi
  SERVER_PID=""
  for _ in $(seq 1 30); do
    curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 || return 0
    sleep 1
  done
  echo "port ${PORT} remained occupied after vLLM shutdown" >&2
  exit 1
}
trap stop_server EXIT

start_server() {
  stop_server
  CUDA_VISIBLE_DEVICES=0 "$VLLM" serve "$1" --port "$PORT" --max-model-len 8192 \
    --gpu-memory-utilization 0.90 --enforce-eager --served-model-name "$2" \
    > "/root/vllm_logs/qae_gate_ablation_198_${PORT}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do
    curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 && return
    sleep 2
  done
  tail -100 "/root/vllm_logs/qae_gate_ablation_198_${PORT}.log"
  exit 1
}

run_stage() {
  local stage=$1 model=$2 out=$3 summary=$4
  shift 4
  "$PYTHON" run_qae_localized.py --stage "$stage" --model "$model" \
    --source "$SOURCE" --out "$out" --summary "$summary" --limit 0 \
    --independent-claims --normalized-d1 --strict-normalization \
    --grounded-normalization --compatible-d1 "$@"
}

prepare_shared_claims() {
  if [[ ! -f "$SEED_OUT" ]]; then
    run_stage hard qwen "$SEED_OUT" "$SEED_SUMMARY"
  fi
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  run_stage claims qwen "$SEED_OUT" "$SEED_SUMMARY"
}

run_config() {
  local name=$1
  shift
  local out="${PREFIX}_${name}.json"
  local summary="${PREFIX}_${name}_summary.json"
  if [[ ! -f "$out" ]]; then
    cp -p "$SEED_OUT" "$out"
  fi

  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  run_stage normalize qwen "$out" "$summary" "$@"
  run_stage localize qwen "$out" "$summary" "$@"
  for spec in \
    "qwen:$QWEN_MODEL:Qwen/Qwen2.5-7B-Instruct" \
    "mathstral:$MATHSTRAL_MODEL:Mathstral-7B" \
    "biomedical_llama:$BIOMISTRAL_MODEL:BioMistral-7B"; do
    IFS=: read -r key model served <<< "$spec"
    start_server "$model" "$served"
    run_stage verify "$key" "$out" "$summary" "$@"
  done
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  run_stage ledger qwen "$out" "$summary" "$@"
  run_stage guard qwen "$out" "$summary" "$@"
  run_stage clean qwen "$out" "$summary" "$@"
  run_stage rebuttal qwen "$out" "$summary" "$@"
  run_stage pool qwen "$out" "$summary" "$@"
  run_stage summary qwen "$out" "$summary" "$@"
}

prepare_shared_claims
run_config control --no-coreference-gate --no-field-span-gate --no-hbr-dedup
run_config coreference --no-field-span-gate --no-hbr-dedup
run_config coreference_span --no-hbr-dedup
run_config coreference_span_hbr
