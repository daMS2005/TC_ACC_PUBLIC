"""Short stable handles for ids a model must reference but should not retype.

Asset ids here are long and mostly prose. A model asked to copy them into an
answer keeps the numbers and rewrites the words, which is why this codebase
grew digit-based and suffix-based repair for near-miss ids. A handle removes
the failure class instead of repairing it: the prompt lists each asset with a
short handle (``a17``), the model answers in handles, and the deterministic
side owns the mapping back to real ids. There is nothing to mistype and
nothing to repair.

Handles are transport, not identity. Artifacts persist real ids only; a
handle never leaves the model boundary it was minted for, and the legend is
rebuilt deterministically from the same ordered listing each time.
"""

from __future__ import annotations

from collections.abc import Iterable


def build_asset_handles(
    asset_ids: Iterable[str],
    *,
    prefix: str = "a",
) -> dict[str, str]:
    """Real id -> handle, numbered in the supplied order.

    The order must be deterministic (the same listing the prompt shows), so
    a rebuilt legend resolves a saved answer identically.
    """

    handles: dict[str, str] = {}
    index = 0
    for asset_id in asset_ids:
        value = str(asset_id or "").strip()
        if not value or value in handles:
            continue
        index += 1
        handles[value] = f"{prefix}{index}"
    return handles


def resolve_handles(
    values: list[str],
    handles: dict[str, str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Translate handle references back to real ids.

    A value that already is a known real id passes through untouched, so
    payloads written before handles existed -- or a model that answered with
    full ids anyway -- stay valid. A value that is neither a known id nor a
    known handle also passes through, for the caller's own unknown-reference
    reporting; inventing a resolution here would hide an invention there.
    """

    by_handle = {
        handle.casefold(): asset_id
        for asset_id, handle in handles.items()
    }
    resolved: list[str] = []
    translated: list[tuple[str, str]] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in handles:
            resolved.append(text)
            continue
        target = by_handle.get(text.casefold())
        if target is None:
            resolved.append(text)
            continue
        resolved.append(target)
        translated.append((text, target))
    return resolved, translated
