#!/usr/bin/env python3
"""
Backward-compatible launcher for ConfigMergeTool.

After ``pip install configmergetool``, use the ``configmergetool`` command
instead of running this script directly.

Both invocation styles are equivalent::

    python ConfigMergeTool.py --audit-config-file audit.json
    configmergetool --audit-config-file audit.json

All logic lives in ``configmerge.cli``.  This file exists solely for
users who run the tool from the cloned source directory without installing.
"""

import sys

from configmerge.cli import main

if __name__ == "__main__":
    sys.exit(main())
