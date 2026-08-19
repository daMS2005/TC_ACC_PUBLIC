from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path


def clean_text(text: str | None) -> str:
    value = re.sub(r"http\S+|www\S+", "", text or "")
    value = re.sub(r"[\\/*?:\"<>|]", "", value)
    value = re.sub(r"[\r\n\t]+", " ", value)
    return re.sub(r"\s{2,}", " ", value).strip()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_numeric_hash(value: str, digits: int = 12) -> str:
    if digits < 1:
        raise ValueError("digits must be >= 1")
    modulus = 10**digits
    numeric = int(stable_hash(value), 16) % modulus
    return f"{numeric:0{digits}d}"


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:96] or fallback


def source_identity_seed(
    *,
    source_type: str,
    source_name: str,
    external_id: str | None = None,
    source_url: str | None = None,
    title: str | None = None,
    raw_text: str | None = None,
) -> str:
    primary_value = external_id or source_url or clean_text(raw_text or title)
    return f"{source_type}:{source_name}:{primary_value}"


def source_segment_id(
    *,
    source_type: str,
    source_name: str,
    external_id: str | None = None,
    source_url: str | None = None,
    title: str | None = None,
    raw_text: str | None = None,
    digits: int = 12,
) -> str:
    prefix = slugify(source_name or source_type, fallback="source")[:24]
    numeric = stable_numeric_hash(
        source_identity_seed(
            source_type=source_type,
            source_name=source_name,
            external_id=external_id,
            source_url=source_url,
            title=title,
            raw_text=raw_text,
        ),
        digits=digits,
    )
    return f"{prefix}-{numeric}"


def lead_segment_id(lead: dict) -> str:
    metadata = lead.get("metadata") or {}
    existing = metadata.get("case_id") or metadata.get("source_segment_id")
    if existing:
        return str(existing)
    return source_segment_id(
        source_type=str(lead.get("source_type", "")),
        source_name=str(lead.get("source_name", "")),
        external_id=str(lead.get("external_id", "") or "") or None,
        source_url=str(lead.get("source_url", "") or "") or None,
        title=str(lead.get("title", "") or "") or None,
        raw_text=str(lead.get("raw_text", "") or "") or None,
    )


def ensure_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


SOURCE_FINGERPRINT_SUFFIXES = frozenset(
    {".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".py"}
)
# Generated trees that live inside the source roots we walk. They are outputs,
# not authorship: `public/runs/<run_id>` is written by the staging step of the
# very render being fingerprinted, so walking it would make the fingerprint
# depend on its own result, and node_modules is ~40k files of vendor code that
# package-lock.json already pins.
SOURCE_FINGERPRINT_SKIPPED_DIRS = frozenset(
    {"node_modules", "runs", "dist", "build", ".tmp", "__pycache__"}
)


def source_tree_fingerprint(
    project_root: str | Path,
    relative_paths: tuple[str, ...],
) -> str:
    """Hash the authored source at `relative_paths` under `project_root`.

    Content-addressed and order-independent: every file is hashed by content
    and keyed by its repo-relative path, then the records are sorted, so the
    answer depends on what the source says and never on filesystem walk order
    or mtime. A path may name a file or a directory; directories are walked for
    source suffixes only, skipping the generated trees above.

    Missing paths are recorded as missing rather than skipped, so deleting the
    last component of a root still moves the fingerprint.
    """

    root = Path(project_root).expanduser().resolve()
    records: list[dict[str, object]] = []
    for relative_path in sorted(set(relative_paths)):
        target = (root / relative_path).resolve()
        if target.is_file():
            candidates = [target]
        elif target.is_dir():
            candidates = [
                item
                for item in target.rglob("*")
                if item.is_file()
                and item.suffix.casefold() in SOURCE_FINGERPRINT_SUFFIXES
                and not (
                    SOURCE_FINGERPRINT_SKIPPED_DIRS
                    & set(item.relative_to(target).parts[:-1])
                )
            ]
        else:
            records.append({"path": relative_path, "missing": True})
            continue
        for item in candidates:
            records.append(
                {
                    "path": str(item.relative_to(root)),
                    "sha256": _file_sha256(item),
                }
            )
    records.sort(key=lambda record: str(record["path"]))
    return stable_hash(
        json.dumps(
            records,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summarize(text: str, max_chars: int = 360) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def debug_log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[TC_ACC {timestamp}] {message}", file=sys.stderr, flush=True)


@contextmanager
def timed_debug(label: str):
    start = time.perf_counter()
    debug_log(f"START {label}")
    try:
        yield
    except Exception as exc:
        elapsed = time.perf_counter() - start
        debug_log(f"FAIL {label} after {elapsed:.2f}s :: {exc}")
        raise
    elapsed = time.perf_counter() - start
    debug_log(f"END {label} after {elapsed:.2f}s")
