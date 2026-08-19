"""Tolerant coercion of model-supplied values.\n\nShared leaf module: no tc_acc imports, safe for any layer to use.\nMoved verbatim from tc_acc.agents.nodes so extracted modules can share\nthe single implementation without importing the agent monolith.\n"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def as_mapping(value: Any) -> dict:
    """A dict copy of ``value``, or an empty dict when it is not a mapping.

    ``as_mapping(payload.get("x"))`` looks defensive and is not: a model that
    answers a mapping field with a sentence hands ``dict`` a string, and
    ``dict("no route found")`` raises "dictionary update sequence element #0
    has length 1". That killed a run 65 minutes in, inside the animation
    selector, with no indication of which field was at fault. A wrong-typed
    field is treated as an absent one, which every caller here already handles.
    """

    return dict(value) if isinstance(value, Mapping) else {}


# Deprecation aliases. These two began as module-private helpers and were
# imported across 71 module boundaries before being promoted on 2026-08-18 --
# an underscore name used that widely is public API wearing the wrong prefix.
# The aliases keep any straggler alive; new code imports the public names.
_safe_float = safe_float
_as_mapping = as_mapping
