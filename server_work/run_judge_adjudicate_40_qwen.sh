#!/bin/bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1
cd /root/GoA
python run_judge_adjudicate.py   --data_path data/test/GPQA_test.json   --full_results outputs/hard_full_198.json   --idxs_path calibration40_idxs.json   --out outputs/judge_adjudicate_40_qwen.json   --workers 6 --judge qwen
