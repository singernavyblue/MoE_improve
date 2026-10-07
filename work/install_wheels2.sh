#!/bin/bash
# vllm 0.27.0 requires torch==2.13.0. Download the correct torch wheel and install both.
TORCH_URL="https://mirrors.aliyun.com/pypi/packages/50/c0/68a84105e1fcb8970144b388ff3d3e5dc15a3be28c1e247841f7d7247e41/torch-2.13.0-cp310-cp310-manylinux_2_28_x86_64.whl"
TORCH_WHL="/root/wheels/torch-2.13.0-cp310-cp310-manylinux_2_28_x86_64.whl"

curl -4 -L --retry 3 -o "$TORCH_WHL" "$TORCH_URL"
echo "torch size: $(stat -c%s "$TORCH_WHL" 2>/dev/null)"

source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
python -m pip install -i https://mirrors.aliyun.com/pypi/simple --timeout 180 \
  /root/wheels/vllm-0.27.0-cp38-abi3-manylinux_2_28_x86_64.whl \
  "$TORCH_WHL"

python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__, '| cuda', torch.cuda.is_available())" && echo "WHEELS2_OK"
