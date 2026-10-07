#!/bin/bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1
cd /root/GoA
python run_hard_full.py \
  --data_path data/test/GPQA_test.json \
  --out outputs/hard_full_198.json \
  --workers 6
