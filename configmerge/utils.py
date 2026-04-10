"""
configmerge.utils
~~~~~~~~~~~~~~~~~
Shared filesystem helpers.
"""

from __future__ import annotations
import hashlib
import os
import re
import shutil
import logging
from typing import Optional


# ---------------------------------------------------------------------------
# API version upgrade detection
# ---------------------------------------------------------------------------

# Matches a version token like -1.2.17  _2.3  -2.17.1  (separator + digits.dots)
_ARTIFACT_VER_RE = re.compile(r'(?<=[a-zA-Z\d])([-_])(\d+(?:\.\d+){0,4})(?=[-_.]|\.jar|\.war|\.zip|$)')


_JAVA_FQCN_RE = re.compile(
    r'^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*){1,}'  # ≥2 lowercase package segments
    r'(?:\.[A-Z][a-zA-Z0-9]*)+$'                  # ≥1 CamelCase class segment
)


def is_java_fqcn(value: str) -> bool:
    """Return True if *value* looks like a Java fully-qualified class name.

    Detection criteria:
    - At least two lowercase package segments separated by dots.
    - Followed by at least one CamelCase segment (class / inner class).
    - No whitespace, no path separators, no version tokens.

    Examples that match:
        com.roamware.sds2.lib.util.openapi.LogPlugin
        com.mobileum.app.icamp.api.gen.server.v1.NETWORK.iCampNetworkSettings_EP

    Examples that do NOT match:
        log4j-1.2.17.jar  (contains hyphen/version)
        3.14               (starts with digit)
        simple.value       (only one package segment before class)
    """
    if not value or " " in value or "/" in value or "\\" in value:
        return False
    # Allow $ for inner classes (e.g. Outer$Inner) but treat as non-matching otherwise
    return bool(_JAVA_FQCN_RE.match(value))


def detect_api_version_upgrade(base_val: str, release_val: str) -> bool:
    """Return True when *base_val* and *release_val* look like different versions
    of the same third-party artifact (e.g. ``log4j-1.2.17.jar`` vs
    ``log4j2-2.17.1.jar``, ``commons-lang-2.6.jar`` vs ``commons-lang3-3.12.jar``).

    Detection criteria:
    1. Both values contain a version-like token (digits.dots after a separator).
    2. The version tokens differ.
    3. After stripping the version token the stems share a common prefix of at
       least 3 characters and differ in at most 3 trailing characters (to handle
       generation suffixes like ``2`` or ``3`` appended to the library name).
    """
    if base_val == release_val:
        return False

    bm = _ARTIFACT_VER_RE.search(base_val)
    rm = _ARTIFACT_VER_RE.search(release_val)
    if not bm or not rm:
        return False

    b_ver = bm.group(2)
    r_ver = rm.group(2)
    if b_ver == r_ver:
        return False  # same version — not an upgrade

    # Stems = everything up to (but not including) the version separator
    b_stem = base_val[: bm.start()].lower()
    r_stem = release_val[: rm.start()].lower()

    if not b_stem or not r_stem:
        return False

    # Normalise: keep only alphanumeric + path separators
    b_norm = re.sub(r'[^a-z0-9/\\._-]', '', b_stem)
    r_norm = re.sub(r'[^a-z0-9/\\._-]', '', r_stem)

    if not b_norm or not r_norm:
        return False

    shorter = b_norm if len(b_norm) <= len(r_norm) else r_norm
    longer  = r_norm if len(b_norm) <= len(r_norm) else b_norm

    # The longer stem must start with the shorter stem and add at most 3 chars
    # (e.g. 'log4j' → 'log4j2'; 'commons-lang' → 'commons-lang3')
    if longer.startswith(shorter) and len(longer) - len(shorter) <= 3:
        return len(shorter) >= 3

    # Exact stem match (same library name, just version number differs)
    return b_norm == r_norm

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
