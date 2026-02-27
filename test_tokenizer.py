from transformers import AutoTokenizer
import os
from huggingface_hub import snapshot_download
import json
import traceback

model_path = "unsloth/GLM-OCR"
logger = print

local_dir = snapshot_download(
    repo_id=model_path,
    allow_patterns=["tokenizer*", "*.json", "*.model", "*.py"],
    local_dir="/tmp/local_glm",
)

config_path = os.path.join(local_dir, "tokenizer_config.json")
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        local_config = json.load(f)
    if local_config.get('tokenizer_class') in ('TokenizersBackend', 'PreTrainedTokenizerFast'):
        local_config['tokenizer_class'] = 'ChatGLMTokenizer'
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(local_config, f, ensure_ascii=False)
        logger("Patched tokenizer_config.json tokenizer_class -> ChatGLMTokenizer")

import sys
sys.path.insert(0, local_dir)
try:
    import tokenization_chatglm
    print("Successfully imported tokenization_chatglm natively")
except Exception:
    print("Native import of tokenization_chatglm failed:")
    traceback.print_exc()

try:
    tokenizer = AutoTokenizer.from_pretrained(local_dir, trust_remote_code=True, use_fast=False)
    print("Success local:", tokenizer)
except Exception as e:
    print("Failed local_dir:")
    traceback.print_exc()
