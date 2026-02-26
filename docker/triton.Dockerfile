FROM nvcr.io/nvidia/tritonserver:24.01-py3

ENV PIP_DEFAULT_TIMEOUT=1000

RUN pip3 install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.2.0 \
    torchvision==0.17.0

RUN pip3 install --no-cache-dir \
    pillow==10.2.0 \
    transformers==4.37.2 \
    accelerate==0.27.2 \
    sentencepiece==0.2.0 \
    safetensors==0.4.2 \
    huggingface_hub==0.20.3 \
    tiktoken==0.6.0
