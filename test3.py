from transformers import AutoTokenizer
model_path = "unsloth/GLM-OCR"
try:
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    print("Successfully loaded tokenizer:", type(tokenizer))
except Exception as e:
    import traceback
    traceback.print_exc()
