"""
configmerge.utils
~~~~~~~~~~~~~~~~~
Shared filesystem helpers.
"""

from __future__ import annotations
import hashlib
import os
import shutil
import logging
from typing import Optional


def ensure_dir(path: str) -> None:
    """Create parent directories for *path* if they do not exist."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def copy_file(src: str, dst: str, logger: Optional[logging.Logger] = None) -> None:
    """Copy *src* to *dst*, creating parent dirs as needed.  Streams content."""
    if logger:
        logger.info(f"[COPY] {src} → {dst}")
    ensure_dir(dst)
    shutil.copy2(src, dst)


def safe_realpath(base_dir: str, rel_path: str) -> Optional[str]:
    """
    Join *base_dir* and *rel_path* and return the canonical absolute path.
    Returns None if the result escapes *base_dir* (path-traversal guard).
    """
    base_real = os.path.realpath(base_dir)
    joined    = os.path.realpath(os.path.join(base_dir, rel_path))
    if not joined.startswith(base_real + os.sep) and joined != base_real:
        return None
    return joined


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_tag(elem) -> str:
    """Strip XML namespace from element tag."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
