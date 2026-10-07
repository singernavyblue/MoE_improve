#!/bin/bash
mkdir -p /root/wheels
VLLM_URL="https://mirrors.aliyun.com/pypi/packages/df/8a/2147c8227501b76829950857a839bebfe7f3f736704649c98bdec3d219f8/vllm-0.27.0-cp38-abi3-manylinux_2_28_x86_64.whl"
TORCH_URL="https://mirrors.aliyun.com/pypi/packages/f9/1e/18a9b10b4bd34f12d4e561c52b0ae7158707b8193c6cfc0aad2b48167090/torch-2.11.0-cp310-cp310-manylinux_2_28_x86_64.whl"

echo "downloading vllm..."
curl -4 -L --retry 3 -C - -o /root/wheels/vllm.whl "$VLLM_URL"
echo "vllm size: $(stat -c%s /root/wheels/vllm.whl 2>/dev/null)"

echo "downloading torch..."
curl -4 -L --retry 3 -C - -o /root/wheels/torch.whl "$TORCH_URL"
echo "torch size: $(stat -c%s /root/wheels/torch.whl 2>/dev/null)"

source /root/miniconda3/etc/profile.d/conda.sh
conda activate goa
python -m pip install -i https://mirrors.aliyun.com/pypi/simple --timeout 180 /root/wheels/vllm.whl /root/wheels/torch.whl
python -m pip install -i https://mirrors.aliyun.com/pypi/simple --timeout 180 transformers datasets fire loguru huggingface-hub requests numpy math-verify
echo "PIP_DONE"
