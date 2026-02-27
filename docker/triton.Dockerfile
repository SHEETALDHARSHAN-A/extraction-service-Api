FROM nvcr.io/nvidia/tritonserver:24.01-py3

ENV PIP_DEFAULT_TIMEOUT=1000

RUN pip3 install \
    --index-url https://download.pytorch.org/whl/cu121 \
    torch==2.4.0 \
    torchvision==0.19.0

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
