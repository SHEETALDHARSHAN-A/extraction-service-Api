# syntax=docker/dockerfile:1.6
FROM nvcr.io/nvidia/tritonserver:24.01-py3

ENV PIP_DEFAULT_TIMEOUT=1000 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# pip in this base image can fail uninstalling distro-provided packages
# (e.g. blinker). Upgrade pip first and preinstall a pip-managed blinker.
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade pip setuptools wheel && \
    pip3 install --ignore-installed blinker

# ── PyTorch (GPU-enabled, validated in tritonserver:24.01-py3) ─────────────
# torch 2.3.1 + cu121 has been validated to load correctly with CUDA in this
# base image (torch.cuda.is_available() == True).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.3.1 \
    torchvision==0.18.1

# ── Core ML / HF stack ────────────────────────────────────────────────────
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
    pillow==10.2.0 \
    transformers==4.49.0 \
    accelerate==0.33.0 \
    sentencepiece==0.2.0 \
    safetensors==0.4.5 \
    huggingface_hub==0.29.0 \
    tiktoken==0.6.0 \
    tokenizers==0.21.0 \
    protobuf \
    einops

# ── GLM-OCR official SDK ───────────────────────────────────────────────────
# Install from official source repository (PyPI package may be unavailable in
# some environments/base images).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
    --ignore-installed \
    git+https://github.com/zai-org/GLM-OCR.git

# ── Fix broken deps from GLM-OCR --ignore-installed ──────────────────────
# The --ignore-installed flag above can clobber safetensors with an
# incompatible version. Re-pin to the version expected by transformers.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --force-reinstall safetensors==0.4.5 && \
    pip3 install --force-reinstall scipy==1.11.4

# ── PaddleOCR / PaddlePaddle (CPU wheel; GPU done at runtime if needed) ───
# Used for PP-DocLayout-V3 layout detection (stage-1 of the two-stage pipeline)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
    paddlepaddle==2.6.2 \
    paddleocr==2.8.1

# ── Misc helpers used by model.py ─────────────────────────────────────────
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install \
    "numpy<2" \
    requests

# Ensure CUDA runtime from image toolkit is resolved first by Triton Python backend
ENV LD_LIBRARY_PATH=/usr/local/cuda/targets/x86_64-linux/lib:${LD_LIBRARY_PATH}

# ── Pre-cache GLM-OCR model weights (~0.9B params â‰ˆ 1.8 GB bf16) ──────────
# Bake weights into the image so container startup doesn't download from HF.
# This is critical for fast GPU inference — without it, every restart waits
# minutes for a multi-GB download.
ENV HF_HOME=/opt/hf-cache
RUN python3 -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('zai-org/GLM-OCR', cache_dir='/opt/hf-cache') \
" || echo 'WARN: HF pre-cache failed — model will download at runtime'

# Fix CUDA symbol resolution: torch's pip-installed CUDA runtime (nvidia-cuda-runtime-cu12)
# provides cudaGetDriverEntryPointByVersion which the system's CUDA 12.3 libcudart lacks.
# torch/lib does NOT contain libcudart — the actual runtime is in nvidia/cuda_runtime/lib/.
# This ENV is placed AFTER the pre-cache RUN to preserve layer cache.
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/nvidia/cuda_runtime/lib:/usr/local/lib/python3.10/dist-packages/torch/lib:${LD_LIBRARY_PATH}
