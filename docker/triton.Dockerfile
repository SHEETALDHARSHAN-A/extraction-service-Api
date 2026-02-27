FROM nvcr.io/nvidia/tritonserver:24.01-py3

ENV PIP_DEFAULT_TIMEOUT=1000

RUN pip3 install \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.2.0 \
    torchvision==0.17.0

RUN pip3 install \
    pillow==10.2.0 \
    transformers==4.44.0 \
    accelerate==0.33.0 \
    sentencepiece==0.2.0 \
    safetensors==0.4.2 \
    huggingface_hub==0.24.0 \
    tiktoken==0.6.0 \
    tokenizers==0.19.1 \
    einops
