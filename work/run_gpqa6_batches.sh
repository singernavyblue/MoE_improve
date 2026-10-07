#!/bin/bash
set -u

GOA=/root/GoA
CHUNKS=/root/autodl-tmp/gpqa_chunks
RESULTS=/root/autodl-tmp/gpqa_results6
PY=/root/autodl-tmp/goa/bin/python

mkdir -p "$RESULTS"
cd "$GOA"

for i in 1 2 3 4; do
  cp "$CHUNKS/GPQA_test_part$i.json" "$GOA/data/test/GPQA_test.json"
  echo "===== BATCH $i START $(date '+%F %T') =====" >> "$RESULTS/batches.log"
  env HF_HOME=/root/autodl-tmp/hf HF_HUB_OFFLINE=1 "$PY" main.py \
    --data GPQA --eval test \
    --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul \
    --meta_llm qwen \
    --graph_pooling_method mean --top_k 3 --threshold 0.05 \
    --rounds 1 --temperature 0.7 --max_tokens 800 \
    --num_proc 6 --seed 0 >> "$RESULTS/batch$i.log" 2>&1
  echo "===== BATCH $i END $(date '+%F %T') =====" >> "$RESULTS/batches.log"
  mv "$GOA"/outputs/GPQA/test/*.json "$RESULTS/batch$i.json" 2>/dev/null
  grep "Overall Accuracy" "$RESULTS/batch$i.log" | tail -1 >> "$RESULTS/accuracies.txt"
done

echo "ALL_BATCHES_DONE $(date '+%F %T')" >> "$RESULTS/batches.log"
