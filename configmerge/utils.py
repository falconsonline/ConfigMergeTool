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

# Optional chardet for encoding detection (BUG-B)
try:
    import chardet as _chardet  # type: ignore
except ImportError:
    _chardet = None


def ensure_dir(path: str) -> None:
    """Create parent directories for *path* if they do not exist.

    Thread-safe on all platforms: wraps the rare TOCTOU race on Windows
    where exist_ok=True can still raise FileExistsError.
    """
    parent = os.path.dirname(path)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except FileExistsError:
            pass


def open_text(path: str) -> str:
    """Read *path* as text, auto-detecting encoding.

    Tries utf-8-sig (strips BOM) first.  Falls back to latin-1 on
    UnicodeDecodeError so ISO-8859 / latin-1 files (e.g. files containing
    © 0xa9) are handled without errors.  If *chardet* is installed it is
    used as an intermediate step for more accurate detection.

    Returns the full file contents as a str.
    """
    # --- attempt 1: utf-8-sig (handles UTF-8 with or without BOM)
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except UnicodeDecodeError:
        pass

    # --- attempt 2: chardet (if available)
    if _chardet is not None:
        try:
            with open(path, "rb") as fb:
                raw = fb.read()
            detected = _chardet.detect(raw)
            enc = (detected.get("encoding") or "latin-1").lower()
            if enc not in ("utf-8", "utf-8-sig", "ascii"):
                return raw.decode(enc, errors="replace")
        except Exception:
            pass

    # --- fallback: latin-1 (accepts any byte sequence)
    with open(path, encoding="latin-1") as f:
        return f.read()


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
    """Return the MD5 hex digest of *path* (used internally for change detection)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_sha256(path: str) -> str:
    """Return the SHA-256 hex digest of *path* (used in audit binary comparison)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_tag(elem) -> str:
    """Strip XML namespace from element tag."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
