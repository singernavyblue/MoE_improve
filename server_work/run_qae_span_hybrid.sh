#!/usr/bin/env bash
# Lossless-span / selective-conflict GPQA runner.
#
# Unlike run_qae_gate_ablation_198.sh, this does not generate a complete
# model-authored claim ledger.  It writes every source response into a
# program-owned offset span ledger, retrieves cross-model span candidates only
# for answer-disagreement records, and materialises structured claims only
# after an admitted span conflict.
set -euo pipefail

GOA_DIR=${GOA_DIR:-/root/GoA}
PYTHON=${PYTHON:-/root/autodl-tmp/goa/bin/python}
VLLM=${VLLM:-/root/autodl-tmp/goa/bin/vllm}
# This runner is intentionally paired with the isolated implementation file,
# so launching it cannot accidentally replace or alter an active legacy run.
RUNNER=${RUNNER:-run_qae_span_hybrid.py}
PORT=${PORT:-8000}
SOURCE=${SOURCE:-outputs/qae_pooling_full_source_hard_v2.json}
PREFIX=${PREFIX:-outputs/qae_span_hybrid_198}
OUT=${OUT:-${PREFIX}.json}
SUMMARY=${SUMMARY:-${PREFIX}_summary.json}
LIMIT=${LIMIT:-0}
ONLY_DISAGREEMENT=${ONLY_DISAGREEMENT:-1}
DIAGNOSIS_GATE=${DIAGNOSIS_GATE:-1}
QWEN_MODEL=${QWEN_MODEL:-/root/autodl-tmp/hf/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28}
MATHSTRAL_MODEL=${MATHSTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--mistralai--Mathstral-7B-v0.1/snapshots/ec3a48484ef241dfe03282edcb0f25e564923823}
BIOMISTRAL_MODEL=${BIOMISTRAL_MODEL:-/root/autodl-tmp/hf/hub/models--BioMistral--BioMistral-7B/snapshots/9a11e1ffa817c211cbb52ee1fb312dc6b61b40a5}
SPAN_CANDIDATE_LIMIT=${SPAN_CANDIDATE_LIMIT:-24}

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
    > "/root/vllm_logs/qae_span_hybrid_${PORT}.log" 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 120); do
    curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1 && return
    sleep 2
  done
  tail -100 "/root/vllm_logs/qae_span_hybrid_${PORT}.log"
  exit 1
}

run_stage() {
  local stage=$1 model=$2
  local -a stage_args=(
    --stage "$stage" --model "$model"
    --source "$SOURCE" --out "$OUT" --summary "$SUMMARY" --limit "$LIMIT"
    --span-hybrid --span-candidate-limit "$SPAN_CANDIDATE_LIMIT"
  )
  if [[ "$ONLY_DISAGREEMENT" == "1" ]]; then
    stage_args+=(--only-disagreement)
  fi
  if [[ "$DIAGNOSIS_GATE" == "1" ]]; then
    stage_args+=(--diagnosis-gate)
  fi
  "$PYTHON" "$RUNNER" "${stage_args[@]}"
}

# The first three stages are fully program-owned and do not require vLLM.
run_stage hard qwen
run_stage spans qwen
run_stage span_candidates qwen
if [[ "$DIAGNOSIS_GATE" == "1" ]]; then
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
  run_stage diagnose qwen
else
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
fi
run_stage localize qwen
if run_stage verify_needed qwen; then
  for spec in \
    "qwen:$QWEN_MODEL:Qwen/Qwen2.5-7B-Instruct" \
    "mathstral:$MATHSTRAL_MODEL:Mathstral-7B" \
    "biomedical_llama:$BIOMISTRAL_MODEL:BioMistral-7B"; do
    IFS=: read -r key model served <<< "$spec"
    start_server "$model" "$served"
    run_stage verify "$key"
  done
  # The last verifier may be non-Qwen; the remaining stages use Qwen.
  start_server "$QWEN_MODEL" Qwen/Qwen2.5-7B-Instruct
else
  # Qwen is still serving from diagnosis/localization, so avoid a needless
  # model restart when there is no D1 evidence to verify.
  echo "[verify] skipped=no_pending_d1_evidence"
fi
run_stage ledger qwen
run_stage guard qwen
run_stage clean qwen
run_stage rebuttal qwen
run_stage pool qwen
run_stage summary qwen
