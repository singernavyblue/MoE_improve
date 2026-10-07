#!/bin/bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1
cd /root/GoA
python run_hard_ab.py \
  --data_path data/test/GPQA_test.json \
  --idxs_path hard_ab_13_idxs.json \
  --out outputs/hard_ab_13.json \
  --reuse_initials outputs/teacher_val_40.json \
  --workers 3
