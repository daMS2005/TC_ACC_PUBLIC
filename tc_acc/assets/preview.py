from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PIL import Image

from ..user_agent import user_agent
from ..config import Settings
from ..run_logging import log_event
from ..media import (
    extract_media_frame,
    probe_media_audio,
    probe_media_duration,
)
from .case_video import CASE_VIDEO_ACQUISITION, download_case_video
from .case_video_window import (
    case_video_needs_window,
    materialize_case_video_window,
    visual_goal_lead,
)
from ..utils import ensure_dir, slugify
from .similarity import image_similarity_report


def build_candidate_previews(candidate: dict[str, Any], settings: Settings, episode_dir: Path) -> dict[str, Any]:
    preview_dir = ensure_dir(episode_dir / "asset_previews" / str(candidate.get("candidate_id", "candidate")))
    media_kind = str(candidate.get("media_kind", "image"))
    source_url = str(candidate.get("download_url") or candidate.get("preview_url") or "")
    result = {
        "candidate_id": candidate.get("candidate_id"),
        "media_kind": media_kind,
        "source_url": source_url,
        "local_source_path": "",
        "image_paths": [],
        "frames": [],
        "audio": {},
        "issues": [],
    }
    if not source_url:
        result["issues"].append("No preview/download URL available.")
        return result
    try:
        local_source = Path(
            materialize_candidate_source(candidate, episode_dir, settings)
        )
        result["local_source_path"] = str(local_source)
        if media_kind == "video":
            # How long the file actually is, measured off the bytes on disk.
            # The provider's `duration_seconds` is a search-result claim in
            # whole seconds -- Pexels reported 8 for a 7.68s file, the clip
            # selector filled the whole claim, and the render died at frame
            # 5711 for it. The probe was already being paid for to place the
            # preview frames; now its answer is recorded instead of discarded.
            duration_seconds = probe_media_duration(local_source)
            result["measured_duration_seconds"] = round(duration_seconds, 3)
            result["frames"] = _extract_video_frames(
                local_source,
                preview_dir,
                settings.asset_preview_video_frame_count,
                duration_seconds=duration_seconds,
            )
            # The one moment the bytes are on disk and nothing has decided
            # anything about them yet. Whether this clip carries sound is a
            # property of the file, so it is measured here rather than guessed
            # later from the URL or the asset type.
            result["audio"] = _inspect_candidate_audio(local_source)
        else:
            preview_path = _make_image_preview(local_source, preview_dir / "preview.jpg")
            result["frames"] = [
                {
                    "frame_index": 1,
                    "timestamp_seconds": 0.0,
                    "path": preview_path,
                }
            ]
        result["image_paths"] = [
            str(frame["path"])
            for frame in result["frames"]
            if str(frame.get("path") or "")
        ]
        result["frame_similarity"] = image_similarity_report(list(result["image_paths"]))
    except Exception as exc:
        result["issues"].append(f"Preview extraction failed: {exc}")
    return result


def _inspect_candidate_audio(local_source: Path) -> dict[str, Any]:
    """What this clip's soundtrack is, recorded beside its frames.

    A failure here is annotated, never fatal. The audio probe is additional
    information about an asset whose pictures are already good; refusing the
    asset because ffmpeg could not measure its loudness would trade a usable
    shot for a field nobody has consumed yet.
    """

    try:
        return probe_media_audio(local_source).as_dict()
    except RuntimeError as exc:
        return {
            "has_audio_stream": False,
            "audio_measured": False,
            "audio_is_silent": False,
            "carries_audible_sound": False,
            "audio_probe_reason": f"Audio probe failed: {exc}",
        }


# What each image format actually starts with. This is the same table
# stage-assets.mjs applies in `sniffImageExtension`, and it is here because
# that sniffer should never have been the first place it was needed: the
# staged file is named from a preview source that was itself named from the
# provider's claim. Measured on run v2-full5-20260811-01, five of the twenty
# three surviving `source.jpg` files under `asset_previews/` are not JPEG --
# three PNG and two WebP. PIL opens them anyway because `Image.open` sniffs
# content, so the misnaming costs nothing here and everything downstream,
# where a name is all the next stage has to go on.
_IMAGE_MAGIC: tuple[tuple[str, int, bytes], ...] = (
    (".png", 0, b"\x89PNG\r\n\x1a\n"),
    (".jpg", 0, b"\xff\xd8\xff"),
    (".gif", 0, b"GIF8"),
    (".avif", 4, b"ftypavif"),
    (".avif", 4, b"ftypavis"),
    (".bmp", 0, b"BM"),
)


def sniff_image_extension(path: Path) -> str | None:
    """The extension these bytes actually earn, or None when unrecognised.

    Returns the true extension whatever the file is called; the caller decides
    whether that differs from the claim. Kept byte-for-byte in step with
    `sniffImageExtension` in remotion/scripts/stage-assets.mjs -- two sniffers
    disagreeing about one file is worse than either one being wrong.
    """

    try:
        with open(path, "rb") as handle:
            head = handle.read(16)
    except OSError:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    for extension, offset, magic in _IMAGE_MAGIC:
        if head[offset : offset + len(magic)] == magic:
            return extension
    return None


def _describe_undecodable(path: Path) -> str:
    """What a file that PIL refused actually turned out to be.

    Run v2-full5-20260811-01 lost candidates to a bare "cannot identify image
    file <path>", which names the file and says nothing about it. Every one of
    the 58 that could still be traced was an HTML document -- 43 googletagmanager
    `ns.html` tracking iframes, 9 youtube `/embed/` pages, the rest widget and
    player embeds -- harvested as image candidates and correctly refused. That
    took a byte-level dig to establish because the message withheld the one
    fact that explains it. It does not withhold it now.
    """

    try:
        with open(path, "rb") as handle:
            head = handle.read(64)
    except OSError:
        return "unreadable"
    if not head:
        return "an empty file"
    sniffed = sniff_image_extension(path)
    if sniffed:
        return f"{sniffed.lstrip('.').upper()} that PIL could not decode"
    stripped = head.lstrip()[:32].lower()
    if stripped.startswith((b"<!doctype", b"<html", b"<head", b"<script")):
        return "an HTML document, not an image"
    if stripped.startswith((b"<?xml", b"<svg")):
        return "an SVG document, which PIL cannot rasterise"
    if head[:5] == b"%PDF-":
        return "a PDF, not an image"
    if head[4:8] == b"ftyp":
        return "an ISO media container, not an image"
    return f"not a recognised image format (starts with {head[:8]!r})"


def _existing_source(preview_dir: Path) -> Path | None:
    """Any already-materialized source, whatever content named it.

    Resume has to find the file the previous pass wrote, and that name now
    depends on what the bytes were. Looking only for `source.jpg` would
    re-download every WebP on every resume and leave the old file orphaned
    beside the new one.
    """

    candidates = sorted(
        path
        for path in preview_dir.glob("source.*")
        if path.is_file() and path.stat().st_size > 0
    )
    return candidates[0] if candidates else None


def materialize_candidate_source(
    candidate: dict[str, Any],
    episode_dir: Path,
    settings: Settings | None = None,
) -> str:
    """Ensure a reviewed candidate's original media is present on disk."""

    media_kind = str(candidate.get("media_kind") or "image").casefold()
    suffix = ".mp4" if media_kind == "video" else ".jpg"
    preview_dir = ensure_dir(
        episode_dir
        / "asset_previews"
        / str(candidate.get("candidate_id") or "candidate")
    )
    existing = _existing_source(preview_dir)
    if existing is not None:
        return str(existing)
    local_source = preview_dir / f"source{suffix}"

    source_url = str(
        candidate.get("download_url")
        or candidate.get("preview_url")
        or ""
    ).strip()
    if not source_url:
        raise ValueError("No preview/download URL available.")
    if _is_case_video_candidate(candidate):
        # A case-video candidate holds a page URL, not a media URL: the probe
        # deliberately stopped at metadata. Fetching it is an extractor's job,
        # and it happens here, at the first moment the bytes are actually
        # wanted, so an unreviewed candidate costs a probe and no download.
        if settings is None:
            raise ValueError(
                "Case-video candidates need settings to reach the extractor."
            )
        _materialize_case_video(candidate, local_source, settings)
        return str(local_source)
    _download(source_url, local_source)
    if media_kind != "video":
        local_source = _rename_to_sniffed_extension(local_source)
    return str(local_source)


def _rename_to_sniffed_extension(local_source: Path) -> Path:
    """Rename a downloaded image to the extension its bytes earn.

    Only images. A video's container is read by ffprobe, which sniffs for
    itself and never consults the name. Nothing is renamed when the bytes are
    unrecognised: an HTML error page saved as `source.jpg` has no honest
    extension to move to, and it is about to be refused by name in the
    preview step anyway.
    """

    sniffed = sniff_image_extension(local_source)
    claimed = local_source.suffix.casefold()
    if not sniffed or sniffed == claimed or (sniffed == ".jpg" and claimed == ".jpeg"):
        return local_source
    renamed = local_source.with_suffix(sniffed)
    try:
        local_source.replace(renamed)
    except OSError:
        return local_source
    log_event(
        "asset_preview_source_renamed_to_sniffed_format",
        claimed=claimed,
        sniffed=sniffed,
        path=str(renamed),
    )
    return renamed


def _materialize_case_video(
    candidate: dict[str, Any],
    local_source: Path,
    settings: Settings,
) -> None:
    """Fetch a case video, windowed to the work order's goal when it is long.

    The probe already reported the duration without downloading anything, so
    the decision about whether this is a forty-minute broadcast is made before
    a single byte moves. A short video is fetched whole, exactly as before. A
    long one is windowed, and the range it was taken from is written back onto
    the candidate as `source_window` -- source URL plus time range is the
    citation, and it has to travel with the file.
    """

    source_url = str(
        candidate.get("download_url") or candidate.get("preview_url") or ""
    ).strip()
    metadata = candidate.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    duration_seconds = float(candidate.get("duration_seconds") or 0.0)
    if not case_video_needs_window(duration_seconds, settings):
        download_case_video(source_url, local_source, settings)
        return

    window = materialize_case_video_window(
        source_url,
        local_source,
        visual_goal_lead(
            title=str(candidate.get("title") or ""),
            asset_use=str(candidate.get("asset_type") or ""),
            reason=str(candidate.get("query") or ""),
            context_text=str(metadata.get("source_snippet") or ""),
        ),
        settings,
        duration_seconds=duration_seconds,
    )
    if not window.windowed:
        # No usable window means the reviewed candidate turned out not to show
        # what the work order asked for anywhere in its runtime. Staging the
        # whole video instead would hand the clip selector forty unreviewed
        # minutes, which is the outcome the windowing exists to prevent.
        raise RuntimeError(
            f"No part of {source_url} matched the work order's visual goal: "
            f"{window.reason}"
        )
    metadata["source_window"] = window.source_window()
    metadata["case_video_window"] = window.as_dict()
    candidate["metadata"] = metadata
    candidate["duration_seconds"] = window.duration_seconds


def _is_case_video_candidate(candidate: dict[str, Any]) -> bool:
    metadata = candidate.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return str(metadata.get("acquisition") or "") == CASE_VIDEO_ACQUISITION


# Previews are downloaded from several candidates at once. Hosts that serve
# free media police that hard -- Wikimedia answers with HTTP 429 and asks for
# fewer, smaller requests -- and a 429 is recorded as a failed asset, so a burst
# silently destroys usable candidates rather than merely slowing them down.
# Downloads are therefore capped per host, and a 429 is waited out rather than
# treated as a verdict on the asset.
_HOST_DOWNLOAD_LIMITS: dict[str, int] = {
    "upload.wikimedia.org": 1,
    "commons.wikimedia.org": 1,
    "commons.m.wikimedia.org": 1,
}
_DEFAULT_HOST_DOWNLOAD_LIMIT = 3
_DOWNLOAD_RETRY_DELAYS_SECONDS = (2.0, 5.0, 12.0)
_MAX_RETRY_AFTER_SECONDS = 30.0

# The same deadline the provider slots carry, for the same reason. A download
# holds its host slot for one bounded transfer, but "bounded" is doing less
# work here than it looks: the socket timeout below is per read(), so a server
# that dribbles a byte at a time resets it forever and the holder never
# finishes. Add an abandoned worker -- whose thread stays alive holding this
# semaphore -- and an unbounded acquire would wedge every later download from
# that host for the rest of the run.
HOST_SLOT_WAIT_TIMEOUT_SECONDS = 900.0

_host_slot_lock = threading.Lock()
_host_slots: dict[str, threading.Semaphore] = {}


class HostSlotUnavailableError(RuntimeError):
    """A host's download slot never came free; the holder is presumed hung."""


def _host_slot(host: str) -> threading.Semaphore:
    key = (host or "").casefold()
    with _host_slot_lock:
        slot = _host_slots.get(key)
        if slot is None:
            slot = threading.Semaphore(
                _HOST_DOWNLOAD_LIMITS.get(key, _DEFAULT_HOST_DOWNLOAD_LIMIT)
            )
            _host_slots[key] = slot
        return slot


@contextmanager
def _held_host_slot(host: str) -> Iterator[None]:
    """Hold a host's download slot, or give up on a deadline."""

    slot = _host_slot(host)
    if not slot.acquire(timeout=HOST_SLOT_WAIT_TIMEOUT_SECONDS):
        log_event(
            "host_slot_wait_timeout",
            host=host,
            timeout_seconds=HOST_SLOT_WAIT_TIMEOUT_SECONDS,
        )
        raise HostSlotUnavailableError(
            f"No download slot for {host or '<unknown host>'} came free "
            f"within {HOST_SLOT_WAIT_TIMEOUT_SECONDS:.0f}s; a holder is "
            "presumed hung, so this download was skipped rather than "
            "waited on."
        )
    try:
        yield
    finally:
        slot.release()


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    raw = None
    try:
        raw = error.headers.get("Retry-After") if error.headers else None
    except Exception:  # noqa: BLE001
        raw = None
    if not raw:
        return None
    try:
        return max(0.0, min(float(str(raw).strip()), _MAX_RETRY_AFTER_SECONDS))
    except (TypeError, ValueError):
        return None


def _download(url: str, output_path: Path) -> None:
    host = urlsplit(url).hostname or ""
    with _held_host_slot(host):
        last_error: Exception | None = None
        for attempt in range(len(_DOWNLOAD_RETRY_DELAYS_SECONDS) + 1):
            try:
                _download_once(url, output_path)
                return
            except urllib.error.HTTPError as exc:
                # 429 says "slow down", not "this asset is unusable".
                if exc.code != 429 or attempt >= len(
                    _DOWNLOAD_RETRY_DELAYS_SECONDS
                ):
                    raise
                last_error = exc
                delay = _retry_after_seconds(exc)
                if delay is None:
                    delay = _DOWNLOAD_RETRY_DELAYS_SECONDS[attempt]
                time.sleep(delay)
        if last_error is not None:
            raise last_error


def _download_once(url: str, output_path: Path) -> None:
    _validate_remote_http_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent("asset-preview")})
    opener = urllib.request.build_opener(_ValidatedRedirectHandler())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".download",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as output:
            with opener.open(request, timeout=60) as response:
                _validate_remote_http_url(str(response.geturl()))
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        if temporary_path.stat().st_size <= 0:
            raise ValueError("Downloaded preview media is empty.")
        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


class _ValidatedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validate_remote_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_remote_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Preview URL must use HTTP or HTTPS.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Preview URL must contain a public host without embedded credentials.")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ValueError(f"Preview host could not be resolved: {parsed.hostname}") from exc
    if not addresses:
        raise ValueError(f"Preview host did not resolve to an address: {parsed.hostname}")
    for address_text in addresses:
        address = ipaddress.ip_address(address_text.split("%", 1)[0])
        if not address.is_global:
            raise ValueError(f"Preview URL resolved to a non-public address: {address}")


def discard_preview_source(preview: dict[str, Any], episode_dir: Path) -> bool:
    source_path = str(preview.get("local_source_path") or "").strip()
    if not source_path:
        return False
    path = Path(source_path)
    preview_root = (episode_dir / "asset_previews").resolve()
    try:
        resolved_path = path.resolve(strict=False)
        resolved_path.relative_to(preview_root)
    except (OSError, ValueError):
        return False
    if not resolved_path.name.startswith("source."):
        return False
    resolved_path.unlink(missing_ok=True)
    preview["local_source_path"] = ""
    preview["source_media_removed"] = True
    return True


def _flatten_for_review(image: "Image.Image") -> "Image.Image":
    """Drop transparency in a way that keeps the picture visible.

    `convert("RGB")` discards the alpha channel and keeps whatever RGB sits
    *underneath* a transparent pixel. For a glyph cut out of a solid tile --
    every app icon and logo on the web -- that underlying colour is the tile
    itself, so the glyph vanishes and the preview becomes a blank rectangle.

    That is not cosmetic. The vision reviewer judges `preview.jpg`, while the
    renderer uses the source file, so a preview that erases its subject means
    the reviewer never sees what ships. On v2-full9-20260817-01 an X app icon
    was scraped from a 403-ing garda.ie page and filed as "derry bus depot
    cctv"; its preview flattened to a plain blue square, 30 assets shared that
    identical square, and the icon reached the screen at 1:17 of the delivered
    episode. Regenerating the preview from the icon reproduces the stored
    square byte for byte -- the reviewer was shown our corruption, not the
    asset, and a reviewer failed by machine echo is our bug, not its.

    Compositing onto white keeps the cut-out visible as its own shape.
    """

    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    canvas.alpha_composite(rgba)
    return canvas.convert("RGB")


def _make_image_preview(input_path: Path, output_path: Path, max_size: tuple[int, int] = (1280, 720)) -> str:
    try:
        image_file = Image.open(input_path)
    except OSError as exc:
        # PIL names the file and stops. What the file turned out to be is the
        # part that tells an operator whether supply was lost to a format the
        # pipeline should handle or to a candidate that was never an image.
        raise ValueError(
            f"{input_path.name} is {_describe_undecodable(input_path)}: {exc}"
        ) from exc
    with image_file as image:
        image = _flatten_for_review(image)
        image.thumbnail(max_size)
        canvas = Image.new("RGB", max_size, (12, 14, 18))
        x = (max_size[0] - image.width) // 2
        y = (max_size[1] - image.height) // 2
        canvas.paste(image, (x, y))
        canvas.save(output_path, quality=88)
    return str(output_path)


def _extract_video_frames(
    input_path: Path,
    output_dir: Path,
    frame_count: int,
    *,
    duration_seconds: float | None = None,
) -> list[dict[str, Any]]:
    duration = (
        duration_seconds
        if duration_seconds and duration_seconds > 0
        else probe_media_duration(input_path)
    )
    count = max(1, frame_count)
    timestamps = [
        (index + 1) * duration / (count + 1)
        for index in range(count)
    ]
    frames: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        raw_path = output_dir / f"frame_{index:02d}_raw.jpg"
        preview_path = output_dir / f"frame_{index:02d}.jpg"
        extract_media_frame(input_path, raw_path, timestamp)
        frames.append(
            {
                "frame_index": index,
                "timestamp_seconds": round(timestamp, 3),
                "path": _make_image_preview(raw_path, preview_path),
            }
        )
        raw_path.unlink(missing_ok=True)
    return frames

