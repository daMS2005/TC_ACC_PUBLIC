from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_provenance(
    path: str | Path,
    *,
    duration_seconds: float,
) -> dict[str, object]:
    target = Path(path)
    stat = target.stat()
    return {
        "path": str(target),
        "sha256": sha256_file(target),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "duration_seconds": round(float(duration_seconds), 3),
    }


def provenance_mismatch(
    path: str | Path | None,
    expected: Any,
) -> str | None:
    target = Path(str(path or ""))
    if not target.is_file() or target.stat().st_size <= 0:
        return f"final video is missing or empty: {target}"
    if not isinstance(expected, dict):
        return "render manifest has no final-video provenance"
    expected_size = int(expected.get("size_bytes") or 0)
    if expected_size <= 0 or not str(expected.get("sha256") or ""):
        return "render manifest has incomplete final-video provenance"
    actual_size = target.stat().st_size
    if actual_size != expected_size:
        return (
            f"final video size changed after render: expected {expected_size}, "
            f"found {actual_size}"
        )
    actual_hash = sha256_file(target)
    expected_hash = str(expected["sha256"])
    if actual_hash != expected_hash:
        return (
            "final video content changed after render: expected sha256 "
            f"{expected_hash}, found {actual_hash}"
        )
    return None
