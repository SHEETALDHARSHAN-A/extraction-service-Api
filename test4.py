from transformers import PreTrainedTokenizerFast
from huggingface_hub import snapshot_download

local_dir = snapshot_download("unsloth/GLM-OCR", allow_patterns=["tokenizer*", "*.json", "*.model", "*.py"])
try:
    tokenizer = PreTrainedTokenizerFast.from_pretrained(local_dir)
    print("PreTrainedTokenizerFast Success:", type(tokenizer))
except Exception as e:
    print("PreTrainedTokenizerFast Failed:")
    import traceback
    traceback.print_exc()
