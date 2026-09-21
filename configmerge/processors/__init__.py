"""
configmerge.processors
~~~~~~~~~~~~~~~~~~~~~~
Processor registry and base class.

Adding a new format:
    1. Create a module in this package.
    2. Define a class that extends BaseProcessor.
    3. Decorate it with @register(".ext1", ".ext2").
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Type

from ..models import MergeConfig, ReportEntry

# extension → processor class
PROCESSOR_REGISTRY: Dict[str, "Type[BaseProcessor]"] = {}


def register(*extensions: str):
    """Class decorator: register a processor for one or more file extensions."""
    def decorator(cls):
        for ext in extensions:
            PROCESSOR_REGISTRY[ext.lower()] = cls
        return cls
    return decorator


class BaseProcessor(ABC):
    """
    Contract every processor must satisfy.
    process() receives one or more base files (Many-to-One) + the release file
    and returns a list of ReportEntry objects.
    """

    @abstractmethod
    def process(
        self,
        base_files: List[str],
        rel_file: str,
        out_file: str,
        config: MergeConfig,
        logger: logging.Logger,
    ) -> List[ReportEntry]:
        ...


# Import processors so their @register decorators execute
from . import kv          # noqa: E402, F401
from . import xml_proc    # noqa: E402, F401
from . import json_proc   # noqa: E402, F401
from . import logrotate   # noqa: E402, F401
from . import generic     # noqa: E402, F401
from . import sstp        # noqa: E402, F401  — Phase 8: .sstp copy-only processor (MOD-5)
