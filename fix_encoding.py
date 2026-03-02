"""Fix mojibake / non-ASCII encoding in model.py so it parses on Linux containers."""
import sys

f = r'c:\Users\MONISH RAJ T\OneDrive\Desktop\IDLE\services\triton-models\glm_ocr\1\model.py'

with open(f, 'r', encoding='utf-8', errors='replace') as fh:
    content = fh.read()

lines = content.split('\n')
fixed = []
for line in lines:
    try:
        line.encode('ascii')
        fixed.append(line)
    except UnicodeEncodeError:
        cleaned = ''
        for ch in line:
            if ord(ch) < 128:
                cleaned += ch
            elif ch in ('\u201c', '\u201d'):
                cleaned += '"'
            elif ch in ('\u2018', '\u2019'):
                cleaned += "'"
            elif ch == '\u2014':
                cleaned += '--'
            elif ch == '\u2013':
                cleaned += '-'
            elif ch == '\u2026':
                cleaned += '...'
            elif ch == '\u2022':
                cleaned += '*'
            elif ch == '\ufffd':
                cleaned += '?'
            else:
                pass  # drop unrecognized non-ASCII
        fixed.append(cleaned)

result = '\n'.join(fixed)
with open(f, 'w', encoding='utf-8', newline='\n') as fh:
    fh.write(result)

print(f'Done. Lines: {len(fixed)}')

import py_compile
try:
    py_compile.compile(f, doraise=True)
    print('SYNTAX OK')
except py_compile.PyCompileError as e:
    print(f'SYNTAX ERROR: {e}')
    sys.exit(1)
