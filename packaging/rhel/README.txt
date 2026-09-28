ConfigMergeTool 3.0.2 — offline bundle for RHEL 8 and RHEL 9
==============================================================

This folder installs ConfigMergeTool on a RHEL 8 or RHEL 9 server that has no
internet access. Everything the tool needs is in wheels/; nothing is
downloaded and no root rights are needed.

Supported
---------
  OS            RHEL 8, RHEL 9 (and compatible: Rocky, AlmaLinux, Oracle Linux)
  CPU           x86_64 or aarch64
  Python        3.9, 3.11 or 3.12 (whichever is installed; newest is used)

  RHEL 8's default /usr/bin/python3 is 3.6, which is too old. Install one of
  these first (needs the administrator, one time):
    RHEL 8:  sudo dnf install python39        (or python3.11 / python3.12)
    RHEL 9:  python3 (3.9) is normally present; python3.11 / python3.12 are
             available with  sudo dnf install python3.11
  On RHEL 8, Python 3.11/3.12 need up-to-date system libraries: if install.sh
  reports that the virtual environment could not be created, the administrator
  runs  sudo dnf update expat  (or a full dnf update).

Tested (2026-09-28, offline pip install, audit + merge smoke test)
------------------------------------------------------------------
  Rocky Linux 8.9 x86_64   Python 3.9, 3.11, 3.12 (with expat updated)
  Rocky Linux 8.9 aarch64  Python 3.9, 3.12 (with expat updated)
  Rocky Linux 9.3 x86_64   Python 3.9 (default python3), 3.11, 3.12
  Rocky Linux 9.3 aarch64  Python 3.12

Install
-------
  tar xzf configmergetool-3.0.2-rhel8-9-offline.tar.gz
  cd configmergetool-3.0.2-rhel8-9-offline
  ./install.sh                       # installs into ~/configmergetool
  ./install.sh /opt/apps/cmt         # or any folder you can write to
  PYTHON=/usr/bin/python3.11 ./install.sh   # choose the Python explicitly

  Then:
    ~/configmergetool/bin/configmergetool --version     # configmergetool 3.0.2

Manual install (same result, without the script)
------------------------------------------------
  python3.9 -m venv ~/configmergetool
  ~/configmergetool/bin/pip install --no-index --no-cache-dir \
      --find-links wheels "configmergetool[encoding]==3.0.2"

What is in wheels/
------------------
  configmergetool-3.0.2   the tool (pure Python)
  openpyxl 3.1.5          Excel reports                 (pure Python)
  et_xmlfile 2.0.0        needed by openpyxl            (pure Python)
  PyYAML 6.0.3            YAML audit and merge          (built per Python/CPU)
  chardet                 file-encoding detection       (7.6.0 for Python 3.11/3.12,
                                                         5.2.0 for Python 3.9)
  pip picks the right PyYAML / chardet wheel for the server's Python and CPU.

Upgrade from an earlier version
-------------------------------
  Run ./install.sh with the same folder: the existing environment is reused and
  ConfigMergeTool 3.0.2 replaces the older version.

Full documentation: ConfigMergeTool-readme.txt and ConfigMergeTool-guide.html
(included in this bundle).
