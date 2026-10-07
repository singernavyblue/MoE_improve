#!/bin/bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
export PATH=/root/miniconda3/envs/goa/bin:$PATH
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 180 \
  vllm torch transformers datasets fire loguru huggingface-hub requests numpy math-verify
echo "PIP_DONE"
