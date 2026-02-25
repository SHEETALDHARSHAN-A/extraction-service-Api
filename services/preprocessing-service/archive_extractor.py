"""
Archive Extraction Module

Handles all compressed file formats with support for:
- ZIP (including nested ZIPs, ZIP inside ZIP)
- RAR
- 7z
- TAR, TAR.GZ, TAR.BZ2, TAR.XZ
- GZ (single file)

Recursively extracts nested archives to a flat list of document files.
"""

import os
import shutil
import zipfile
import tarfile
import gzip
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Supported document extensions (everything we can process)
DOCUMENT_EXTENSIONS = {
    '.pdf', '.docx', '.xlsx', '.pptx',
    '.csv', '.txt',
    '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp',
}

# Archive extensions we recognize
ARCHIVE_EXTENSIONS = {
    '.zip', '.rar', '.7z',
    '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2', '.txz',
}

MAX_NESTING_DEPTH = 10  # Safety limit for recursive extraction


def is_archive(filepath: str) -> bool:
    """Check if a file is an archive by extension."""
    path = Path(filepath)
    # Handle double extensions like .tar.gz
    suffixes = ''.join(path.suffixes).lower()
    if any(suffixes.endswith(ext) for ext in ['.tar.gz', '.tar.bz2', '.tar.xz']):
        return True
    return path.suffix.lower() in ARCHIVE_EXTENSIONS


def is_document(filepath: str) -> bool:
    """Check if a file is a processable document."""
    return Path(filepath).suffix.lower() in DOCUMENT_EXTENSIONS


def extract_archive(archive_path: str, output_dir: str, depth: int = 0) -> list:
    """
    Extract an archive recursively (handles nested archives).

    Returns a list of extracted document file paths.
    """
    if depth > MAX_NESTING_DEPTH:
        logger.warning(f"Max nesting depth ({MAX_NESTING_DEPTH}) reached, skipping: {archive_path}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    ext = Path(archive_path).suffix.lower()
    suffixes = ''.join(Path(archive_path).suffixes).lower()
    documents = []

    logger.info(f"{'  ' * depth}📦 Extracting: {os.path.basename(archive_path)} (depth={depth})")

    try:
        # --- ZIP ---
        if ext == '.zip':
            documents = _extract_zip(archive_path, output_dir, depth)

        # --- RAR ---
        elif ext == '.rar':
            documents = _extract_rar(archive_path, output_dir, depth)

        # --- 7z ---
        elif ext == '.7z':
            documents = _extract_7z(archive_path, output_dir, depth)

        # --- TAR / TAR.GZ / TAR.BZ2 / TAR.XZ ---
        elif ext in ('.tar', '.tgz', '.tbz2', '.txz') or \
             suffixes.endswith('.tar.gz') or suffixes.endswith('.tar.bz2') or suffixes.endswith('.tar.xz'):
            documents = _extract_tar(archive_path, output_dir, depth)

        # --- GZ (single file) ---
        elif ext == '.gz' and '.tar' not in suffixes:
            documents = _extract_gz(archive_path, output_dir, depth)

        # --- BZ2 (single file) ---
        elif ext == '.bz2' and '.tar' not in suffixes:
            documents = _extract_bz2(archive_path, output_dir, depth)

        else:
            logger.warning(f"{'  ' * depth}Unsupported archive format: {ext}")

    except Exception as e:
        logger.error(f"{'  ' * depth}❌ Failed to extract {archive_path}: {e}")

    logger.info(f"{'  ' * depth}✅ Extracted {len(documents)} documents from {os.path.basename(archive_path)}")
    return documents


def _extract_zip(archive_path: str, output_dir: str, depth: int) -> list:
    """Extract ZIP files (handles nested ZIPs recursively)."""
    documents = []
    with zipfile.ZipFile(archive_path, 'r') as zf:
        zf.extractall(output_dir)

    # Walk extracted contents
    for root, dirs, files in os.walk(output_dir):
        for fname in files:
            fullpath = os.path.join(root, fname)
            if is_archive(fullpath):
                # Recursive extraction for nested archives
                nested_dir = fullpath + "_extracted"
                nested_docs = extract_archive(fullpath, nested_dir, depth + 1)
                documents.extend(nested_docs)
                # Clean up the nested archive after extraction
                os.remove(fullpath)
            elif is_document(fullpath):
                documents.append(fullpath)

    return documents


def _extract_rar(archive_path: str, output_dir: str, depth: int) -> list:
    """Extract RAR files using unrar command."""
    documents = []
    try:
        subprocess.run(
            ['unrar', 'x', '-o+', archive_path, output_dir],
            check=True, capture_output=True
        )
    except FileNotFoundError:
        # Try 7z as fallback for RAR
        try:
            subprocess.run(
                ['7z', 'x', f'-o{output_dir}', '-y', archive_path],
                check=True, capture_output=True
            )
        except FileNotFoundError:
            logger.error("Neither 'unrar' nor '7z' is installed. Cannot extract RAR files.")
            return []

    for root, dirs, files in os.walk(output_dir):
        for fname in files:
            fullpath = os.path.join(root, fname)
            if is_archive(fullpath):
                nested_dir = fullpath + "_extracted"
                documents.extend(extract_archive(fullpath, nested_dir, depth + 1))
                os.remove(fullpath)
            elif is_document(fullpath):
                documents.append(fullpath)

    return documents


def _extract_7z(archive_path: str, output_dir: str, depth: int) -> list:
    """Extract 7z files using 7z command."""
    documents = []
    try:
        subprocess.run(
            ['7z', 'x', f'-o{output_dir}', '-y', archive_path],
            check=True, capture_output=True
        )
    except FileNotFoundError:
        logger.error("'7z' is not installed. Cannot extract 7z files.")
        return []

    for root, dirs, files in os.walk(output_dir):
        for fname in files:
            fullpath = os.path.join(root, fname)
            if is_archive(fullpath):
                nested_dir = fullpath + "_extracted"
                documents.extend(extract_archive(fullpath, nested_dir, depth + 1))
                os.remove(fullpath)
            elif is_document(fullpath):
                documents.append(fullpath)

    return documents


def _extract_tar(archive_path: str, output_dir: str, depth: int) -> list:
    """Extract TAR/TAR.GZ/TAR.BZ2/TAR.XZ files."""
    documents = []
    with tarfile.open(archive_path, 'r:*') as tf:
        tf.extractall(output_dir, filter='data')

    for root, dirs, files in os.walk(output_dir):
        for fname in files:
            fullpath = os.path.join(root, fname)
            if is_archive(fullpath):
                nested_dir = fullpath + "_extracted"
                documents.extend(extract_archive(fullpath, nested_dir, depth + 1))
                os.remove(fullpath)
            elif is_document(fullpath):
                documents.append(fullpath)

    return documents


def _extract_gz(archive_path: str, output_dir: str, depth: int) -> list:
    """Extract single-file GZ (not tar.gz)."""
    out_name = Path(archive_path).stem  # Removes .gz
    out_path = os.path.join(output_dir, out_name)

    with gzip.open(archive_path, 'rb') as f_in, open(out_path, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

    if is_archive(out_path):
        return extract_archive(out_path, output_dir, depth + 1)
    elif is_document(out_path):
        return [out_path]
    return []


def _extract_bz2(archive_path: str, output_dir: str, depth: int) -> list:
    """Extract single-file BZ2."""
    import bz2
    out_name = Path(archive_path).stem
    out_path = os.path.join(output_dir, out_name)

    with bz2.open(archive_path, 'rb') as f_in, open(out_path, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

    if is_archive(out_path):
        return extract_archive(out_path, output_dir, depth + 1)
    elif is_document(out_path):
        return [out_path]
    return []


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python archive_extractor.py <archive_path> <output_dir>")
        sys.exit(1)

    docs = extract_archive(sys.argv[1], sys.argv[2])
    print(f"\nExtracted {len(docs)} documents:")
    for d in docs:
        print(f"  {d}")
