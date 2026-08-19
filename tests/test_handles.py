"""Short handles remove the id-transcription failure class at model
boundaries: the model answers in handles, the deterministic side owns the
mapping, and artifacts persist real ids only."""
from __future__ import annotations

from tc_acc.handles import build_asset_handles, resolve_handles


def test_handles_number_in_listing_order_and_dedupe():
    handles = build_asset_handles(
        ["asset-long-one", "", "asset-long-two", "asset-long-one"]
    )
    assert handles == {
        "asset-long-one": "a1",
        "asset-long-two": "a2",
    }


def test_resolution_translates_handles_and_passes_real_ids_through():
    handles = build_asset_handles(["asset-long-one", "asset-long-two"])
    resolved, translated = resolve_handles(
        ["a2", "asset-long-one", "A1"],
        handles,
    )
    assert resolved == [
        "asset-long-two",
        "asset-long-one",
        "asset-long-one",
    ]
    assert translated == [
        ("a2", "asset-long-two"),
        ("A1", "asset-long-one"),
    ]


def test_unknown_references_pass_through_for_reporting():
    handles = build_asset_handles(["asset-long-one"])
    resolved, translated = resolve_handles(
        ["a9", "invented-asset"],
        handles,
    )
    # Inventing a resolution here would hide an invention from the caller's
    # unknown-reference reporting.
    assert resolved == ["a9", "invented-asset"]
    assert translated == []


def test_a_real_id_that_collides_with_a_handle_stays_itself():
    handles = build_asset_handles(["a1", "asset-long-two"])
    # "a1" is simultaneously a real id (first entry) and the handle minted
    # for it; identity wins over transport.
    resolved, translated = resolve_handles(["a1"], handles)
    assert resolved == ["a1"]
    assert translated == []
