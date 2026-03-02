"""Add comprehensive debug to deserialize_bytes_tensor."""
filepath = '/opt/tritonserver/backends/python/triton_python_backend_utils.py'

with open(filepath, 'r') as f:
    content = f.read()

# Replace the existing debug line + start of function body
old = '    import sys as _sys\n    _sys.stderr.write(f"[DESER_DEBUG] called len={len(encoded_tensor)} first20={encoded_tensor[:20]!r}\\n")\n    _sys.stderr.flush()\n    strs = list()'

new = '''    import sys as _sys, traceback as _tb
    _dtype = getattr(encoded_tensor, 'dtype', 'N/A')
    _type = type(encoded_tensor).__name__
    _sys.stderr.write(f"[DESER_DEBUG] type={_type} dtype={_dtype} len={len(encoded_tensor)}\\n")
    if isinstance(encoded_tensor, (bytes, bytearray)):
        _sys.stderr.write(f"[DESER_DEBUG] raw_bytes={encoded_tensor[:40]!r}\\n")
    else:
        _sys.stderr.write(f"[DESER_DEBUG] repr={repr(encoded_tensor)[:200]}\\n")
    _sys.stderr.write(f"[DESER_DEBUG] traceback:\\n{''.join(_tb.format_stack()[-4:])}\\n")
    _sys.stderr.flush()
    strs = list()'''

if old in content:
    content = content.replace(old, new, 1)
    with open(filepath, 'w') as f:
        f.write(content)
    import os, glob
    for f in glob.glob('/opt/tritonserver/backends/python/__pycache__/triton_python*'):
        os.remove(f)
    print("Enhanced debug ADDED")
else:
    print("ERROR: old pattern not found")
    # Show the current state around deserialize
    idx = content.find('def deserialize_bytes_tensor')
    if idx >= 0:
        print(repr(content[idx:idx+500]))
