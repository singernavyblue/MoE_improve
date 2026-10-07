#!/bin/bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export HF_HOME=/root/autodl-tmp/hf
export HF_HUB_OFFLINE=1
cd /root/GoA
python run_topchain_22.py \
  --full_results outputs/hard_full_198.json \
  --out outputs/topchain_22.json \
  --workers 6
