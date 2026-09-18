"""Allow ``python -m configmerge`` as an alternative invocation."""
import sys
from configmerge.cli import main

sys.exit(main())
