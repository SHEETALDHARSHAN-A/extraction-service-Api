#!/usr/bin/env python3
"""Simple fix verification - checks requirements.txt has non-yanked version"""

import re
import sys

# Read requirements.txt
with open("services/post-processing-service/requirements.txt", 'r') as f:
    content = f.read()

print("Requirements.txt content:")
print(content)
print()

# Extract grpcio version
match = re.search(r'grpcio==([0-9.]+)', content)

if not match:
    print("ERROR: grpcio not found in requirements.txt")
    sys.exit(1)

version = match.group(1)
print(f"Found grpcio version: {version}")

# Check if it's the yanked version
if version == "1.78.1":
    print("FAIL: Still using yanked version 1.78.1")
    sys.exit(1)

print(f"PASS: Using non-yanked version {version}")
print()
print("Fix verified: requirements.txt specifies a non-yanked grpcio version")
sys.exit(0)
