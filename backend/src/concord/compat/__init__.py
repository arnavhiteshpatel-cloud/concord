"""Compatibility registry (Milestone 5, workstream F): which integrations exist, what each one
is, and the validation level each has reached, derived from evidence (docs/COMPATIBILITY.md).

``model`` and ``rules`` are pure; ``build`` generates ``compat/registry.json``; ``live``
loads it and attaches what this installation actually has.
"""

from concord.compat.model import LEVELS, Entry, Evidence, Registry, Sources
from concord.compat.rules import CompatError, derive_level

__all__ = ["LEVELS", "CompatError", "Entry", "Evidence", "Registry", "Sources", "derive_level"]
