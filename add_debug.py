"""Add debug print to deserialize_bytes_tensor."""
filepath = '/opt/tritonserver/backends/python/triton_python_backend_utils.py'

with open(filepath, 'r') as f:
    content = f.read()

# Add a debug print right after the docstring
old_marker = '    strs = list()\n    offset = 0\n    val_buf = encoded_tensor'
new_marker = '    import sys as _sys\n    _sys.stderr.write(f"[DESER_DEBUG] called len={len(encoded_tensor)} first20={encoded_tensor[:20]!r}\\n")\n    _sys.stderr.flush()\n    strs = list()\n    offset = 0\n    val_buf = encoded_tensor'

if old_marker in content:
    content = content.replace(old_marker, new_marker, 1)
    with open(filepath, 'w') as f:
        f.write(content)
    import os, glob
    for f in glob.glob('/opt/tritonserver/backends/python/__pycache__/triton_python*'):
        os.remove(f)
        print(f"Removed: {f}")
    print("Debug print ADDED")
else:
    print("ERROR: marker not found")
    idx = content.find('def deserialize_bytes_tensor')
    if idx >= 0:
        print(repr(content[idx:idx+400]))
