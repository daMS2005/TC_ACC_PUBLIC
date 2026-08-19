from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from .models import to_plain, utc_now_iso
from .utils import ensure_dir

T = TypeVar("T")


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_plain(payload), indent=2, ensure_ascii=True)
    with locked_path(target):
        _write_text_locked(target, text)
    return target


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text_if_changed(path: str | Path, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(target):
        _write_text_locked(target, text)
    return target


def update_json(
    path: str | Path,
    update: Callable[[Any], Any],
    *,
    default: Any,
    archive_existing: bool = True,
) -> Any:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(target):
        current = read_json(target) if target.exists() else default
        updated = update(current)
        text = json.dumps(to_plain(updated), indent=2, ensure_ascii=True)
        _write_text_locked(
            target,
            text,
            archive_existing=archive_existing,
        )
    return updated


@contextmanager
def locked_path(path: str | Path) -> Iterator[None]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / f".{target.name}.lock"
    with lock_path.open("a+b") as lock_handle:
        flock(lock_handle.fileno(), LOCK_EX)
        try:
            yield
        finally:
            flock(lock_handle.fileno(), LOCK_UN)


def _write_text_locked(
    target: Path,
    text: str,
    *,
    archive_existing: bool = True,
) -> None:
    if target.exists() and target.read_text(encoding="utf-8") == text:
        _log_artifact_write("artifact_unchanged", target, bytes_written=0)
        return
    archive_path = (
        _archive_existing_artifact(target)
        if archive_existing
        else ""
    )
    _atomic_write_text(target, text)
    _log_artifact_write("artifact_written", target, bytes_written=len(text.encode("utf-8")), archive_path=archive_path)


def _atomic_write_text(target: Path, text: str) -> None:
    fd, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_path, target)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _archive_existing_artifact(target: Path) -> str:
    if not target.exists() or not target.is_file():
        return ""
    run_id = _current_run_id()
    stamp = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    history_dir = ensure_dir(target.parent / ".history")
    archive_path = history_dir / f"{target.name}.{stamp}.bak"
    if archive_path.exists():
        return str(archive_path)
    archive_path.write_bytes(target.read_bytes())
    _log_artifact_write("artifact_archived", target, bytes_written=archive_path.stat().st_size, archive_path=str(archive_path))
    return str(archive_path)


def _current_run_id() -> str:
    try:
        from .run_logging import current_run_id
    except Exception:
        return ""
    return current_run_id()


def _log_artifact_write(event_type: str, path: Path, *, bytes_written: int, archive_path: str = "") -> None:
    try:
        from .run_logging import log_detail, log_event
    except Exception:
        return
    payload = {
        "path": str(path),
        "artifact_name": path.name,
        "bytes_written": bytes_written,
        "archive_path": archive_path,
    }
    log_event(event_type, **payload)
    log_detail(event_type, **payload)


class ArtifactStore:
    def __init__(
        self,
        data_dir: Path,
        outputs_dir: Path,
        *,
        canonical_data_dir: Path | None = None,
    ):
        self.data_dir = ensure_dir(data_dir)
        self.outputs_dir = ensure_dir(outputs_dir)
        # A V2 run re-roots data_dir at data/v2_runs/<run_id> so its artifacts
        # cannot collide with another run's. Anything bought from a metered
        # provider must not be scoped that way: it is the same bytes for every
        # run, and a per-run copy means paying for it again. Such stores hang
        # off the canonical data dir, which is the scoped dir itself unless a
        # caller says otherwise.
        self.canonical_data_dir = ensure_dir(
            canonical_data_dir if canonical_data_dir is not None else data_dir
        )

    def shared_dir(self) -> Path:
        """Root for cross-run stores that outlive any single run."""

        return self.canonical_data_dir

    def run_dir(self, run_id: str) -> Path:
        return ensure_dir(self.data_dir / "runs" / run_id)

    def leads_dir(self) -> Path:
        return ensure_dir(self.data_dir / "leads")

    def cases_dir(self) -> Path:
        return ensure_dir(self.data_dir / "cases")

    def episode_dir(self, episode_id: str) -> Path:
        return ensure_dir(self.outputs_dir / "episodes" / episode_id)

    def save_lead(self, lead_id: str, payload: Any) -> Path:
        return write_json(self.leads_dir() / f"{lead_id}.json", payload)

    def save_case_artifact(self, case_id: str, name: str, payload: Any) -> Path:
        return write_json(ensure_dir(self.cases_dir() / case_id) / f"{name}.json", payload)

    def save_episode_artifact(self, episode_id: str, name: str, payload: Any) -> Path:
        return write_json(self.episode_dir(episode_id) / f"{name}.json", payload)
