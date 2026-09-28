#!/usr/bin/env bash
# ConfigMergeTool 3.0.2 — offline install for RHEL 8 / RHEL 9 (x86_64 or aarch64).
#
#   ./install.sh [INSTALL_DIR]        default INSTALL_DIR: ~/configmergetool
#   PYTHON=/usr/bin/python3.11 ./install.sh     use a specific Python
#
# Creates a virtual environment in INSTALL_DIR and installs ConfigMergeTool and all its
# libraries from ./wheels. No internet access and no root rights are needed; nothing is
# written outside INSTALL_DIR (pip's cache is disabled).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${1:-$HOME/configmergetool}"
VERSION="3.0.2"

pick_python() {
    local candidates=("${PYTHON:-}" python3.12 python3.11 python3.9 python3)
    for py in "${candidates[@]}"; do
        [ -n "$py" ] || continue
        command -v "$py" >/dev/null 2>&1 || continue
        if "$py" -c 'import sys, venv; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            command -v "$py"
            return 0
        fi
    done
    return 1
}

if ! PY="$(pick_python)"; then
    cat >&2 <<'MSG'
ERROR: no Python 3.9 or newer found.
  RHEL 8's default python3 is 3.6, which is too old. Ask your administrator to install one:
    RHEL 8:  sudo dnf install python39      (or python3.11 / python3.12)
    RHEL 9:  sudo dnf install python3       (3.9; or python3.11 / python3.12)
  Then run this script again, or point it at the interpreter:
    PYTHON=/usr/bin/python3.11 ./install.sh
MSG
    exit 1
fi

echo "Python      : $PY ($("$PY" -c 'import platform; print(platform.python_version())'))"
echo "Install into: $INSTALL_DIR"

if [ ! -x "$INSTALL_DIR/bin/python" ]; then
    if ! "$PY" -m venv "$INSTALL_DIR"; then
        cat >&2 <<'MSG'
ERROR: could not create the virtual environment.
  RHEL 8 with Python 3.11/3.12: this usually means the system libraries are older than the
  Python package (e.g. expat). Ask your administrator to run:
    sudo dnf update expat            (or a full  sudo dnf update)
  and make sure the pip package for that Python is installed, e.g.  python3.12-pip
MSG
        rm -rf "$INSTALL_DIR"
        exit 1
    fi
fi

"$INSTALL_DIR/bin/python" -m pip install --no-index --no-cache-dir \
    --find-links "$HERE/wheels" "configmergetool[encoding]==$VERSION"

echo
"$INSTALL_DIR/bin/configmergetool" --version
cat <<MSG

Installed. Run it as:
  $INSTALL_DIR/bin/configmergetool --help
To type just "configmergetool" from any folder, link it onto your PATH:
  mkdir -p ~/.local/bin && ln -sf "$INSTALL_DIR/bin/configmergetool" ~/.local/bin/configmergetool
MSG
