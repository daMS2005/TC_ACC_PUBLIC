"""Gather everything a finished episode needs for upload into one folder.

A completed run leaves the pieces correct but scattered: the video sits under
``renders/<run-id>/``, the thumbnail beside the episode, and the title,
description, tags and chapters inside ``metadata_package.json``. Publishing
then means opening three directories and a JSON file.

This assembles a single folder that can be opened once and dragged from. It
copies rather than references, because the point is a folder that survives the
run directory being cleaned up.

Nothing here decides anything. Every value is read from artifacts the pipeline
already wrote; if a piece is missing, the bundle records it as missing rather
than inventing a placeholder that would be pasted into YouTube by accident.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .storage import ArtifactStore


@dataclass
class PublishBundle:
    """What was assembled, and what could not be."""

    episode_id: str
    bundle_dir: Path
    video_path: Path | None = None
    thumbnail_path: Path | None = None
    title: str = ""
    title_options: list[str] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    pinned_comment: str = ""
    sources: list[str] = field(default_factory=list)
    chapter_lines: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """A bundle is postable only with a video and something to call it."""
        return self.video_path is not None and bool(self.title)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _place(source: Path, target: Path) -> Path:
    """Hardlink the file into the bundle, copying if that is not possible.

    A render is hundreds of megabytes and a hardlink is instant and free, but
    it only works within one filesystem -- and outputs/ is a symlink into the
    shared checkout on this machine, so the fallback is not theoretical.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
    return target


def _timecode(seconds: float) -> str:
    """YouTube chapter timecode: M:SS under an hour, H:MM:SS at or over it."""
    total = max(int(seconds), 0)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _chapter_start_seconds(chapter: dict[str, Any]) -> float | None:
    """Seconds from whichever way the writer expressed the start.

    metadata_package.json carries ``start`` as an already-formatted "M:SS" or
    "H:MM:SS" string. Earlier shapes used a numeric ``start_seconds``. Reading
    only the numeric form silently produced an empty chapters.txt from a
    metadata package that had fifty-nine perfectly good chapters in it.
    """
    raw = chapter.get("start_seconds")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    text = str(chapter.get("start") or "").strip()
    if not text:
        return None
    try:
        parts = [int(part) for part in text.split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


# YouTube ignores a chapter list entirely -- not the offending entry, the
# whole list -- unless every chapter is at least this far from the previous
# one, the first starts at zero, and there are at least three.
YOUTUBE_MIN_CHAPTER_GAP_SECONDS = 10.0
YOUTUBE_MIN_CHAPTERS = 3


def _readable_chapters(chapters: list[dict[str, Any]]) -> list[tuple[float, str]]:
    """Every chapter we can read a start and a title from, in order."""
    out: list[tuple[float, str]] = []
    for chapter in chapters:
        start = _chapter_start_seconds(chapter)
        title = str(chapter.get("title") or chapter.get("label") or "").strip()
        if start is None or not title:
            continue
        out.append((start, title))
    return sorted(out, key=lambda pair: pair[0])


def _chapter_lines(chapters: list[dict[str, Any]]) -> list[str]:
    """A list YouTube will actually accept, with the reasoning recorded.

    The writer produced 59 chapters for a 9:55 episode on 2026-08-18 -- 31 of
    the 58 gaps were under ten seconds, and pasting that list would have
    silently produced no chapters at all. Where entries are too close, the
    earlier one is kept: it is the one that marks the beat's start.
    """
    readable = _readable_chapters(chapters)
    kept: list[tuple[float, str]] = []
    for start, title in readable:
        if kept and start - kept[-1][0] < YOUTUBE_MIN_CHAPTER_GAP_SECONDS:
            continue
        kept.append((start, title))
    if kept and kept[0][0] != 0:
        kept.insert(0, (0.0, "Start"))
    if len(kept) < YOUTUBE_MIN_CHAPTERS:
        return []
    return [f"{_timecode(start)} {title}" for start, title in kept]


def _acts_as_chapters(episode_dir: Path) -> list[str]:
    """Chapters from the episode's act structure, not the metadata list.

    The writer's metadata_package.json carries a chapter per narration beat --
    59 of them for a 9:55 episode. Those are not what the viewer sees. The
    episode is cut into acts, and only the acts that earned an act slate are
    marked on screen at all, capped at four (see the act_slate brief: "Five
    acts is a structure the writing does not have").

    So the chapters are the cold open plus each slated act, which is what a
    viewer scrubbing the bar is actually looking for.

    Times come from ``episode_frame`` over the canvas fps rather than from
    narration seconds: the frame is the video's own clock, and the two differ
    wherever anything sits between the hook and the body.
    """
    structure = _read_json(episode_dir / "brand_structure.json")
    acts = ((structure.get("acts") or {}).get("acts")) or []
    if not acts:
        return []
    fps = float((structure.get("canvas") or {}).get("fps") or 0) or 24.0

    plan = _read_json(episode_dir / "brand_treatment_plan.json")
    admitted = ((plan.get("candidates") or {}).get("admitted")) or []
    slated_shots = {
        candidate.get("shot_index")
        for candidate in admitted
        if candidate.get("element") == "act_slate"
    }

    lines: list[str] = []
    for act in acts:
        first = act.get("part_index") == 1
        if not first and act.get("start_shot_index") not in slated_shots:
            continue
        title = str(act.get("title") or "").strip()
        if not title:
            continue
        frame = act.get("episode_frame")
        if frame is None:
            continue
        lines.append(f"{_timecode(float(frame) / fps)} {title}")
    if len(lines) < YOUTUBE_MIN_CHAPTERS:
        return []
    return lines


def _find_video(
    store: ArtifactStore,
    episode_id: str,
    delivery: dict[str, Any],
) -> Path | None:
    """The delivered path first; otherwise the newest render for the episode.

    The manifest is authoritative when it exists, but a run stopped after
    render never wrote one, and that is exactly when someone wants the file.
    """
    declared = delivery.get("local_video_path")
    if declared:
        candidate = Path(str(declared))
        if candidate.exists():
            return candidate
    renders = store.episode_dir(episode_id) / "renders"
    if not renders.is_dir():
        return None
    finals = sorted(
        renders.glob("*/final_video.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return finals[0] if finals else None


def assemble_publish_bundle(
    store: ArtifactStore,
    episode_id: str,
    *,
    bundle_root: Path | None = None,
) -> PublishBundle:
    """Collect a finished episode into one folder ready to upload."""
    episode_dir = store.episode_dir(episode_id)
    root = bundle_root or (store.outputs_dir / "publish")
    bundle_dir = root / episode_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    metadata = _read_json(episode_dir / "metadata_package.json")
    delivery = _read_json(episode_dir / "delivery_manifest.json")

    titles = [str(t) for t in (metadata.get("title_options") or []) if str(t).strip()]
    bundle = PublishBundle(
        episode_id=episode_id,
        bundle_dir=bundle_dir,
        title=titles[0] if titles else "",
        title_options=titles,
        description=str(metadata.get("description") or ""),
        tags=[str(t) for t in (metadata.get("tags") or [])],
        chapters=list(metadata.get("chapters") or []),
        pinned_comment=str(metadata.get("pinned_comment") or ""),
        sources=[str(s) for s in (metadata.get("source_list") or [])],
    )

    video = _find_video(store, episode_id, delivery)
    if video:
        bundle.video_path = _place(video, bundle_dir / f"{episode_id}.mp4")
    else:
        bundle.missing.append("video")

    thumbnail = episode_dir / "thumbnail.png"
    if thumbnail.exists():
        bundle.thumbnail_path = _place(thumbnail, bundle_dir / "thumbnail.png")
    else:
        bundle.missing.append("thumbnail")

    for label, value in (
        ("title", bundle.title),
        ("description", bundle.description),
        ("pinned_comment", bundle.pinned_comment),
    ):
        if not value:
            bundle.missing.append(label)
    if not bundle.tags:
        bundle.missing.append("tags")
    # The act structure is the episode's real division and matches what is
    # on screen; the metadata list is a per-beat fallback for an episode that
    # never reached brand_structure.
    bundle.chapter_lines = _acts_as_chapters(episode_dir) or _chapter_lines(
        bundle.chapters
    )
    if not bundle.chapter_lines:
        # Present but unreadable counts as missing: an empty chapters.txt
        # beside a populated metadata package is the failure this hides.
        bundle.missing.append("chapters")

    _write_bundle_files(bundle)
    return bundle


def _write_bundle_files(bundle: PublishBundle) -> None:
    """One file per field to paste, plus a sheet and a machine-readable copy."""
    d = bundle.bundle_dir
    (d / "title.txt").write_text(bundle.title + "\n" if bundle.title else "")
    (d / "description.txt").write_text(bundle.description.rstrip() + "\n")
    (d / "tags.txt").write_text(", ".join(bundle.tags) + "\n")
    (d / "pinned_comment.txt").write_text(
        bundle.pinned_comment.rstrip() + "\n" if bundle.pinned_comment else ""
    )
    chapter_lines = bundle.chapter_lines
    (d / "chapters.txt").write_text(
        "\n".join(chapter_lines) + "\n" if chapter_lines else ""
    )
    # The full list, unfiltered, so nothing the writer produced is lost -- it
    # is just not the file you paste.
    readable = _readable_chapters(bundle.chapters)
    if len(readable) > len(chapter_lines):
        (d / "chapters_all.txt").write_text(
            "\n".join(f"{_timecode(start)} {title}" for start, title in readable)
            + "\n"
        )

    payload = {
        "episode_id": bundle.episode_id,
        "ready": bundle.ready,
        "video": str(bundle.video_path) if bundle.video_path else None,
        "thumbnail": (
            str(bundle.thumbnail_path) if bundle.thumbnail_path else None
        ),
        "title": bundle.title,
        "title_options": bundle.title_options,
        "description": bundle.description,
        "tags": bundle.tags,
        "chapters": chapter_lines,
        "pinned_comment": bundle.pinned_comment,
        "sources": bundle.sources,
        "missing": bundle.missing,
    }
    (d / "bundle.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [f"# {bundle.title or bundle.episode_id}", ""]
    if bundle.missing:
        lines += [f"> Missing: {', '.join(bundle.missing)}", ""]
    lines += ["## Files", ""]
    lines += [f"- Video: `{bundle.video_path.name}`" if bundle.video_path else "- Video: MISSING"]
    lines += [
        f"- Thumbnail: `{bundle.thumbnail_path.name}`"
        if bundle.thumbnail_path
        else "- Thumbnail: MISSING"
    ]
    lines += ["", "## Title", ""]
    lines += [bundle.title or "MISSING"]
    if len(bundle.title_options) > 1:
        lines += ["", "Alternatives the writer produced:", ""]
        lines += [f"- {t}" for t in bundle.title_options[1:]]
    lines += ["", "## Description", "", bundle.description or "MISSING"]
    if chapter_lines:
        lines += ["", "## Chapters", "", "```", *chapter_lines, "```"]
    if bundle.tags:
        lines += ["", "## Tags", "", ", ".join(bundle.tags)]
    if bundle.pinned_comment:
        lines += ["", "## Pinned comment", "", bundle.pinned_comment]
    if bundle.sources:
        lines += ["", "## Sources", "", *[f"- {s}" for s in bundle.sources]]
    (d / "PUBLISH.md").write_text("\n".join(lines).rstrip() + "\n")


def format_bundle_summary(bundle: PublishBundle) -> list[str]:
    """What to print when a run finishes, so the folder is one click away."""
    out = [
        "",
        "─" * 60,
        f"READY TO POST  {bundle.episode_id}"
        if bundle.ready
        else f"INCOMPLETE  {bundle.episode_id}",
        "─" * 60,
        f"  folder      {bundle.bundle_dir}",
    ]
    if bundle.video_path:
        size_mb = bundle.video_path.stat().st_size / 1e6
        out.append(f"  video       {bundle.video_path.name}  ({size_mb:.0f} MB)")
    if bundle.thumbnail_path:
        out.append(f"  thumbnail   {bundle.thumbnail_path.name}")
    if bundle.title:
        out.append(f"  title       {bundle.title}")
    if bundle.missing:
        out.append(f"  missing     {', '.join(bundle.missing)}")
    out += [f"  open        open '{bundle.bundle_dir}'", "─" * 60, ""]
    return out


# Directories of derived files that exist only to produce the render. They are
# regenerable from the artifacts that remain, and they dominate the disk: on
# 2026-08-18 a single run held 2.7 GB of asset previews and 621 MB of clip
# frames against a 561 MB finished video.
RECLAIMABLE_DIRS = ("asset_previews", "youtube_clip_frames")

# Render intermediates. final_video.mp4 is assembled from these; once it
# exists they are dead weight. Named explicitly rather than matched by
# pattern, so a new output cannot be deleted by accident.
RENDER_INTERMEDIATES = (
    "body_video.mp4",
    "final_video.rest.mp4",
    "final_video.hook.mp4",
)


@dataclass
class Reclaimed:
    bytes_freed: int = 0
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def gb(self) -> float:
        return self.bytes_freed / 1e9


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _run_is_live(run_dir: Path) -> bool:
    """A run still writing must never have its working files removed.

    Reads the run's own status rather than trusting a process check alone: a
    stale check is worthless, because a new run can start between the check
    and the delete.
    """
    manifest = run_dir / "studio_run.json"
    try:
        return json.loads(manifest.read_text()).get("status") == "running"
    except (OSError, json.JSONDecodeError):
        return False


def reclaim_space(
    outputs_dir: Path,
    data_dir: Path,
    *,
    protect: Path | None = None,
) -> Reclaimed:
    """Delete regenerable render derivatives across every finished run.

    Never touches ``final_video.mp4``, never touches the publish bundle, and
    never touches a run whose manifest still says it is running. Everything
    removed can be rebuilt by re-running the stage that produced it -- at the
    cost of the provider calls, which is why this is a separate step and not
    something a run does to itself.
    """
    result = Reclaimed()
    runs_root = outputs_dir / "v2_runs"
    if not runs_root.is_dir():
        return result
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        if _run_is_live(data_dir / "v2_runs" / run_dir.name):
            result.skipped.append(f"{run_dir.name} (running)")
            continue
        for episode_dir in (run_dir / "episodes").glob("*"):
            if protect and protect == episode_dir:
                pass  # the published episode still gives up its derivatives
            for name in RECLAIMABLE_DIRS:
                target = episode_dir / name
                if not target.is_dir():
                    continue
                size = _dir_size(target)
                shutil.rmtree(target, ignore_errors=True)
                result.bytes_freed += size
                result.removed.append(f"{run_dir.name}/{name}")
            for render_dir in (episode_dir / "renders").glob("*"):
                if not (render_dir / "final_video.mp4").exists():
                    # Without a finished video these are not intermediates --
                    # they are the only copy of the work.
                    result.skipped.append(f"{render_dir.name} (no final video)")
                    continue
                for name in RENDER_INTERMEDIATES:
                    target = render_dir / name
                    if not target.is_file():
                        continue
                    size = target.stat().st_size
                    target.unlink()
                    result.bytes_freed += size
                    result.removed.append(f"{render_dir.name}/{name}")
    return result
