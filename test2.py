import sys
sys.path.append("/tmp/local_glm")
try:
    import tokenization_chatglm
    print("Successfully imported tokenization_chatglm")
    print(dir(tokenization_chatglm))
except Exception as e:
    import traceback
    traceback.print_exc()
