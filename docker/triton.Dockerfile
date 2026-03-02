FROM nvcr.io/nvidia/tritonserver:24.01-py3

ENV PIP_DEFAULT_TIMEOUT=1000 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# pip in this base image can fail uninstalling distro-provided packages
# (e.g. blinker). Upgrade pip first and preinstall a pip-managed blinker.
RUN python3 -m pip install --upgrade pip setuptools wheel && \
    pip3 install --ignore-installed blinker

# ── PyTorch (GPU-enabled, validated in tritonserver:24.01-py3) ─────────────
# torch 2.3.1 + cu121 has been validated to load correctly with CUDA in this
# base image (torch.cuda.is_available() == True).
RUN pip3 install \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.3.1 \
    torchvision==0.18.1

# ── Core ML / HF stack ────────────────────────────────────────────────────
RUN pip3 install \
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
RUN pip3 install \
    --ignore-installed \
    git+https://github.com/zai-org/GLM-OCR.git

# ── PaddleOCR / PaddlePaddle (CPU wheel; GPU done at runtime if needed) ───
# Used for PP-DocLayout-V3 layout detection (stage-1 of the two-stage pipeline)
RUN pip3 install \
    paddlepaddle==2.6.2 \
    paddleocr==2.8.1

# ── Misc helpers used by model.py ─────────────────────────────────────────
RUN pip3 install \
    numpy \
    requests
