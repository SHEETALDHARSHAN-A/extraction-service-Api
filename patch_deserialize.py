"""Patch triton_python_backend_utils.py inside the container to handle
both length-prefixed binary and raw string bytes in deserialize_bytes_tensor."""

import os
import sys

filepath = '/opt/tritonserver/backends/python/triton_python_backend_utils.py'

with open(filepath, 'r') as f:
    lines = f.readlines()

# Find the function start and end
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith('def deserialize_bytes_tensor('):
        start_idx = i
    elif start_idx is not None and end_idx is None:
        # Find the next top-level def or class (not indented inside the function)
        if (line.strip().startswith('def ') or line.strip().startswith('class ')) and not line.startswith(' ') and not line.startswith('\t'):
            end_idx = i
            break

if start_idx is None:
    print("ERROR: deserialize_bytes_tensor not found")
    sys.exit(1)

if end_idx is None:
    end_idx = len(lines)

print(f"Found deserialize_bytes_tensor at lines {start_idx+1}-{end_idx}")

new_func = '''def deserialize_bytes_tensor(encoded_tensor):
    """
    Deserializes an encoded bytes tensor into an
    numpy array of dtype of python objects.
    Handles both length-prefixed binary format and raw string bytes.
    """
    strs = list()
    offset = 0
    val_buf = encoded_tensor
    try:
        while offset < len(val_buf):
            if offset + 4 > len(val_buf):
                raise struct.error("not enough bytes for length prefix")
            l = struct.unpack_from("<I", val_buf, offset)[0]
            # Sanity: length prefix must not exceed remaining buffer
            if l > len(val_buf) - offset - 4:
                raise struct.error("length prefix exceeds buffer")
            offset += 4
            sb = struct.unpack_from("<{}s".format(l), val_buf, offset)[0]
            offset += l
            strs.append(sb)
    except struct.error:
        # Fallback: the buffer is raw string bytes, not length-prefixed.
        return np.array([encoded_tensor], dtype=np.object_)
    return np.array(strs, dtype=np.object_)


'''

lines[start_idx:end_idx] = [new_func]

with open(filepath, 'w') as f:
    f.writelines(lines)

# Remove cached .pyc
cache_dir = os.path.join(os.path.dirname(filepath), '__pycache__')
if os.path.isdir(cache_dir):
    for fname in os.listdir(cache_dir):
        if 'triton_python_backend_utils' in fname:
            p = os.path.join(cache_dir, fname)
            os.remove(p)
            print(f"Removed cache: {p}")

print("PATCHED successfully")
