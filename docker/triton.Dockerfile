FROM nvcr.io/nvidia/tritonserver:24.01-py3

ENV PIP_DEFAULT_TIMEOUT=1000 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# ── PyTorch (CUDA 12.1) ────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.4.0 \
    torchvision==0.19.0

# ── Core ML / HF stack ────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir \
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
# Installs the glmocr package which provides GlmOcr + PP-DocLayout-V3 loader
RUN pip3 install --no-cache-dir \
    glmocr

# ── PaddleOCR / PaddlePaddle (CPU wheel; GPU done at runtime if needed) ───
# Used for PP-DocLayout-V3 layout detection (stage-1 of the two-stage pipeline)
RUN pip3 install --no-cache-dir \
    paddlepaddle==2.6.1 \
    paddleocr==2.8.1

# ── Misc helpers used by model.py ─────────────────────────────────────────
RUN pip3 install --no-cache-dir \
    numpy \
    requests
