"""The upload folder, and the sweep that follows it.

The sweep deletes files, so its guards are the point of most of these: a run
still writing keeps everything, and a render directory with no finished video
keeps everything, because there the "intermediates" are the only copy of the
work.
"""

from __future__ import annotations

import json

from tc_acc.publish import assemble_publish_bundle, reclaim_space
from tc_acc.storage import ArtifactStore

EPISODE = "ep-001"


def _episode(tmp_path, run="run-1", *, with_video=True, with_thumbnail=True):
    """A finished episode in the layout a real run leaves behind."""
    canon_data, canon_out = tmp_path / "data", tmp_path / "outputs"
    store = ArtifactStore(canon_data / "v2_runs" / run, canon_out / "v2_runs" / run)
    episode_dir = store.episode_dir(EPISODE)
    episode_dir.mkdir(parents=True, exist_ok=True)
    (episode_dir / "metadata_package.json").write_text(
        json.dumps(
            {
                "episode_id": EPISODE,
                "title_options": ["The Vanishing", "Second option"],
                "description": "A case from 2009.",
                "tags": ["true crime"],
                "chapters": [
                    {"start_seconds": 95.5, "title": "The night"},
                    {"start_seconds": 3800, "title": "After"},
                ],
                "pinned_comment": "Sources below.",
                "source_list": ["https://example.org/a"],
            }
        )
    )
    render_dir = episode_dir / "renders" / run
    render_dir.mkdir(parents=True)
    if with_video:
        (render_dir / "final_video.mp4").write_bytes(b"F" * 2048)
    (render_dir / "body_video.mp4").write_bytes(b"B" * 4096)
    if with_thumbnail:
        (episode_dir / "thumbnail.png").write_bytes(b"P" * 16)
    previews = episode_dir / "asset_previews"
    previews.mkdir()
    (previews / "a.jpg").write_bytes(b"X" * 8192)
    return store, canon_data, canon_out, episode_dir, render_dir


def test_the_bundle_collects_everything_needed_to_post(tmp_path):
    store, _, canon_out, _, _ = _episode(tmp_path)

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    assert bundle.ready
    assert bundle.missing == []
    assert bundle.title == "The Vanishing"
    names = {path.name for path in bundle.bundle_dir.iterdir()}
    assert {
        f"{EPISODE}.mp4",
        "thumbnail.png",
        "title.txt",
        "description.txt",
        "tags.txt",
        "chapters.txt",
        "PUBLISH.md",
        "bundle.json",
    } <= names


def test_the_folder_carries_no_lock_files(tmp_path):
    """It is opened by a person; a stray .lock beside the video is noise."""
    store, _, canon_out, _, _ = _episode(tmp_path)

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    assert not [p for p in bundle.bundle_dir.iterdir() if p.name.startswith(".")]


def test_chapters_start_at_zero_and_use_hours_past_an_hour(tmp_path):
    """YouTube rejects a chapter list whose first entry is not 0:00."""
    store, _, canon_out, _, _ = _episode(tmp_path)

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    lines = (bundle.bundle_dir / "chapters.txt").read_text().split("\n")
    assert lines[0].startswith("0:00")
    assert "1:35 The night" in lines
    assert "1:03:20 After" in lines


def test_a_missing_piece_is_recorded_rather_than_invented(tmp_path):
    store, _, canon_out, _, _ = _episode(tmp_path, with_thumbnail=False)

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    assert "thumbnail" in bundle.missing
    assert bundle.thumbnail_path is None


def test_an_episode_without_a_video_is_not_ready(tmp_path):
    store, _, canon_out, _, _ = _episode(tmp_path, with_video=False)

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    assert not bundle.ready
    assert "video" in bundle.missing


def test_the_sweep_keeps_the_render_and_drops_the_derivatives(tmp_path):
    store, canon_data, canon_out, episode_dir, render_dir = _episode(tmp_path)
    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    freed = reclaim_space(canon_out, canon_data)

    assert freed.bytes_freed > 0
    assert (render_dir / "final_video.mp4").exists()
    assert not (render_dir / "body_video.mp4").exists()
    assert not (episode_dir / "asset_previews").exists()
    # the collected copy survives the sweep, which is the whole point of
    # bundling before reclaiming
    assert bundle.video_path.exists()
    assert bundle.video_path.stat().st_size == 2048


def test_a_running_run_is_left_alone(tmp_path):
    """Deleting the working files of a live run would break it mid-flight."""
    _, canon_data, canon_out, _, _ = _episode(tmp_path)
    live_data = canon_data / "v2_runs" / "run-live"
    live_data.mkdir(parents=True)
    (live_data / "studio_run.json").write_text(json.dumps({"status": "running"}))
    live_store = ArtifactStore(live_data, canon_out / "v2_runs" / "run-live")
    live_previews = live_store.episode_dir("ep-live") / "asset_previews"
    live_previews.mkdir(parents=True)
    (live_previews / "b.jpg").write_bytes(b"Z" * 1024)

    freed = reclaim_space(canon_out, canon_data)

    assert (live_previews / "b.jpg").exists()
    assert any("running" in entry for entry in freed.skipped)


def test_intermediates_are_kept_when_no_final_video_exists(tmp_path):
    """Without a finished render they are not intermediates -- they are it."""
    _, canon_data, canon_out, _, render_dir = _episode(tmp_path, with_video=False)

    reclaim_space(canon_out, canon_data)

    assert (render_dir / "body_video.mp4").exists()


def test_chapters_written_as_timecode_strings_are_read(tmp_path):
    """metadata_package.json carries `start` as "M:SS", not `start_seconds`.

    Reading only the numeric form produced an empty chapters.txt beside a
    metadata package holding fifty-nine good chapters (2026-08-18).
    """
    store, _, canon_out, episode_dir, _ = _episode(tmp_path)
    payload = json.loads((episode_dir / "metadata_package.json").read_text())
    payload["chapters"] = [
        {"title": "Cold Open", "start": "0:00"},
        {"title": "The shoreline", "start": "0:46"},
        {"title": "Much later", "start": "1:03:20"},
    ]
    (episode_dir / "metadata_package.json").write_text(json.dumps(payload))

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    lines = (bundle.bundle_dir / "chapters.txt").read_text().strip().split("\n")
    assert lines == ["0:00 Cold Open", "0:46 The shoreline", "1:03:20 Much later"]
    assert "chapters" not in bundle.missing


def test_unreadable_chapters_are_reported_as_missing(tmp_path):
    """An empty chapters.txt beside a populated package must not pass silently."""
    store, _, canon_out, episode_dir, _ = _episode(tmp_path)
    payload = json.loads((episode_dir / "metadata_package.json").read_text())
    payload["chapters"] = [{"title": "No start at all"}]
    (episode_dir / "metadata_package.json").write_text(json.dumps(payload))

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    assert "chapters" in bundle.missing


def test_chapters_closer_than_ten_seconds_are_thinned(tmp_path):
    """YouTube ignores the whole list -- not the entry -- if any gap is short.

    A 9:55 episode arrived with 59 chapters and 31 sub-ten-second gaps
    (2026-08-18); pasting it would have produced no chapters at all.
    """
    store, _, canon_out, episode_dir, _ = _episode(tmp_path)
    payload = json.loads((episode_dir / "metadata_package.json").read_text())
    payload["chapters"] = [
        {"title": "Open", "start": "0:00"},
        {"title": "Too close", "start": "0:04"},
        {"title": "Fine", "start": "0:30"},
        {"title": "Also too close", "start": "0:35"},
        {"title": "Fine again", "start": "1:00"},
    ]
    (episode_dir / "metadata_package.json").write_text(json.dumps(payload))

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    lines = (bundle.bundle_dir / "chapters.txt").read_text().strip().split("\n")
    assert lines == ["0:00 Open", "0:30 Fine", "1:00 Fine again"]
    # nothing the writer produced is lost, it is just not the pasteable file
    everything = (bundle.bundle_dir / "chapters_all.txt").read_text()
    assert "0:04 Too close" in everything


def _with_act_structure(episode_dir, *, slated=(15, 30)):
    """brand_structure + treatment plan, in the shape a real run writes."""
    (episode_dir / "brand_structure.json").write_text(
        json.dumps(
            {
                "canvas": {"fps": 24},
                "acts": {
                    "slate_card_ceiling": 4,
                    "acts": [
                        {
                            "part_index": 1,
                            "title": "The cold open",
                            "start_shot_index": 1,
                            "episode_frame": 0,
                        },
                        {
                            "part_index": 2,
                            "title": "A documented trail",
                            "start_shot_index": 15,
                            "episode_frame": 1211,
                        },
                        {
                            "part_index": 3,
                            "title": "The alias",
                            "start_shot_index": 30,
                            "episode_frame": 2651,
                        },
                        {
                            "part_index": 4,
                            "title": "Not slated, not a chapter",
                            "start_shot_index": 44,
                            "episode_frame": 4000,
                        },
                    ],
                },
            }
        )
    )
    (episode_dir / "brand_treatment_plan.json").write_text(
        json.dumps(
            {
                "candidates": {
                    "admitted": [
                        {"element": "act_slate", "shot_index": shot}
                        for shot in slated
                    ]
                    + [{"element": "file_card", "shot_index": 99}]
                }
            }
        )
    )


def test_chapters_come_from_the_acts_the_viewer_can_see(tmp_path):
    """The episode is cut into acts; the metadata list is per-narration-beat.

    A 9:55 episode carried 59 metadata chapters against 4 act slates
    (2026-08-18). The bar should mark the acts.
    """
    store, _, canon_out, episode_dir, _ = _episode(tmp_path)
    _with_act_structure(episode_dir)

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    lines = (bundle.bundle_dir / "chapters.txt").read_text().strip().split("\n")
    assert lines == [
        "0:00 The cold open",
        "0:50 A documented trail",
        "1:50 The alias",
    ]
    assert "Not slated" not in "\n".join(lines)


def test_the_metadata_chapters_are_used_when_there_is_no_act_structure(tmp_path):
    """An episode stopped before brand_structure still gets a usable list."""
    store, _, canon_out, episode_dir, _ = _episode(tmp_path)
    payload = json.loads((episode_dir / "metadata_package.json").read_text())
    payload["chapters"] = [
        {"title": "Open", "start": "0:00"},
        {"title": "Middle", "start": "0:30"},
        {"title": "End", "start": "1:00"},
    ]
    (episode_dir / "metadata_package.json").write_text(json.dumps(payload))

    bundle = assemble_publish_bundle(
        store, EPISODE, bundle_root=canon_out / "publish"
    )

    assert (bundle.bundle_dir / "chapters.txt").read_text().startswith("0:00 Open")
