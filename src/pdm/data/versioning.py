"""Content hash of data files = the data version logged with every experiment."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_md5(p: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def data_version(files: list[Path]) -> str:
    """Short hash over all files (order-independent). Same bytes -> same version."""
    h = hashlib.md5()
    for p in sorted(files, key=lambda x: x.name):
        h.update(p.name.encode())
        h.update(file_md5(p).encode())
    return h.hexdigest()[:12]
