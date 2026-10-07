#!/bin/bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1
cd /root/GoA
python run_hard_weak.py \
  --data_path data/test/GPQA_test.json \
  --idxs_path teacher_val_40_idxs.json \
  --out outputs/hard_weak_40.json \
  --reuse_initials outputs/teacher_val_40.json \
  --workers 6
