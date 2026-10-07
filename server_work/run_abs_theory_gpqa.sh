#!/bin/bash
# Controlled experiment: theory-grounded rubric (Toulmin + SOLO + Facione)
# in ABSOLUTE (no-gold) scoring, vs old theory version in pairwise (34.34%)
# and vs old absolute variants (generic 32.32% / 4dim 37.88%).
# ONLY the judge rubric text + scoring mode changes; pipeline identical.
cd /root/GoA
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1

python main.py --data GPQA --eval test --reference_models qwen,qwen_coder,mathstral,biomedical_llama,finance_llama,saul --meta_llm qwen --graph_pooling_method mean --top_k 3 --threshold 0.05 --rounds 1 --temperature 0.7 --max_tokens 800 --num_proc 80 --seed 0 --edge_mode judge_absolute_theory_rubric 2>&1 | tee /root/goa_abs_theory.log | grep -E "Overall Accuracy|Saving outputs|Error|Traceback"

echo "ABS_THEORY_DONE"
