#!/bin/bash
# Rename downloaded wheels to their proper distribution filenames and install.
source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa

mv /root/wheels/vllm.whl /root/wheels/vllm-0.27.0-cp38-abi3-manylinux_2_28_x86_64.whl
mv /root/wheels/torch.whl /root/wheels/torch-2.11.0-cp310-cp310-manylinux_2_28_x86_64.whl

python -m pip install -i https://mirrors.aliyun.com/pypi/simple --timeout 180 \
  /root/wheels/vllm-0.27.0-cp38-abi3-manylinux_2_28_x86_64.whl \
  /root/wheels/torch-2.11.0-cp310-cp310-manylinux_2_28_x86_64.whl

python -c "import vllm, torch; print('vllm', vllm.__version__, 'torch', torch.__version__)"
echo "WHEELS_INSTALLED"
