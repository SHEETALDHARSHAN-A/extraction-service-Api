import sys
from transformers import AutoTokenizer

try:
    print("Attempting to load tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained('unsloth/GLM-OCR', trust_remote_code=True)
    print("Tokenizer loaded successfully:", type(tokenizer))
except Exception as e:
    print("Error loading tokenizer:", str(e))
    import traceback
    traceback.print_exc()

import json
import urllib.request
import os

print("Trying python patch...")
try:
    # download to local dir
    os.makedirs('local_glm', exist_ok=True)
    req = urllib.request.Request('https://huggingface.co/unsloth/GLM-OCR/raw/main/tokenizer_config.json')
    with urllib.request.urlopen(req) as response:
        config = json.loads(response.read().decode('utf-8'))
        
    config['tokenizer_class'] = 'PreTrainedTokenizerFast'
    
    with open('local_glm/tokenizer_config.json', 'w') as f:
        json.dump(config, f)
        
    req = urllib.request.Request('https://huggingface.co/unsloth/GLM-OCR/raw/main/tokenizer.json')
    with urllib.request.urlopen(req) as response:
        with open('local_glm/tokenizer.json', 'w') as f:
            f.write(response.read().decode('utf-8'))
            
    print("Local tokenizer config created. Validating...")
    tokenizer = AutoTokenizer.from_pretrained('local_glm', trust_remote_code=True)
    print("Local tokenizer loaded:", type(tokenizer))
except Exception as e:
    print("Error with local patch:", str(e))
    import traceback
    traceback.print_exc()
