"""Accept a chapter start however the writer expressed it.

The metadata stage tells its model the format outright -- `{"title": "Chapter
title", "start": "MM:SS"}` -- but the script writer is only asked for a
"chapters array of {title,start}", so nothing tells it which representation to
use. One run answered in seconds:

    chapters.0.start  Input should be a valid string, input_value=0
    chapters.1.start  Input should be a valid string, input_value=105
    ... 8 chapters, 0 to 815 seconds

Monotonic, evenly spaced, and 815s lands at 13:35 inside the 12-18 minute
target: the chapter breakdown was correct in every respect except the type it
arrived as, and the stage failed on all eight at once.

Seconds are converted here rather than rejected. A negative start is left alone
so it still fails, because that is wrong data rather than a different spelling
of the right data.
"""

from __future__ import annotations

import math
from typing import Any


def normalize_chapter_start(value: Any) -> Any:
    """Render a numeric chapter start as ``MM:SS``, leaving anything else be."""

    if value is None:
        return ""
    # bool is an int subclass, and True as a chapter start is not 0:01.
    if isinstance(value, bool):
        return value
    seconds: float | None = None
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str) and value.strip().isdigit():
        seconds = float(value.strip())
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return value
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def normalize_chapter_mapping(value: Any) -> Any:
    """Normalize the ``start`` of one incoming chapter mapping."""

    if not isinstance(value, dict) or "start" not in value:
        return value
    normalized = dict(value)
    normalized["start"] = normalize_chapter_start(normalized["start"])
    return normalized
