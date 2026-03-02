"""Fix the deserialize_bytes_tensor fallback to handle numpy array inputs correctly."""
filepath = '/opt/tritonserver/backends/python/triton_python_backend_utils.py'

with open(filepath, 'r') as f:
    content = f.read()

# Fix the fallback to handle numpy arrays
old = '    except struct.error:\n        # Fallback: the buffer is raw string bytes, not length-prefixed.\n        return np.array([encoded_tensor], dtype=np.object_)'

new = '''    except struct.error:
        # Fallback: the buffer is raw string bytes, not length-prefixed.
        import sys as _sys2
        _sys2.stderr.write(f"[DESER_FALLBACK] struct.error caught, type={type(encoded_tensor).__name__}\\n")
        _sys2.stderr.flush()
        if isinstance(encoded_tensor, np.ndarray):
            # np.array([ndarray], object) creates 2D — use np.empty instead
            result = np.empty(1, dtype=np.object_)
            result[0] = encoded_tensor.tobytes()
            return result
        return np.array([encoded_tensor], dtype=np.object_)'''

if old in content:
    content = content.replace(old, new, 1)
    with open(filepath, 'w') as f:
        f.write(content)
    import os, glob
    for f in glob.glob('/opt/tritonserver/backends/python/__pycache__/triton_python*'):
        os.remove(f)
    print("Fallback FIXED")
else:
    print("ERROR: pattern not found")
    # Debug: show what's around struct.error
    idx = content.find('struct.error')
    if idx >= 0:
        print(repr(content[max(0,idx-100):idx+200]))
    else:
        print("struct.error not found in file at all")
