from __future__ import annotations

from tc_acc.identifiers import (
    distinctive_numbers,
    repair_reference,
    repair_references,
)

APPROVED = {
    "candidate-pexels-hands-tearing-blank-paper-at-cafe-ta-6670603-7617764e",
    "candidate-pexels-hands-consulting-bus-timetable-insid-6421476-9fc1c5ce",
    "candidate-wikimedia-clareen-bus-station-ireland-26498465-12d2b64e",
}


def test_repairs_the_id_that_ended_a_run():
    # Dropped prefix, description paraphrased rather than copied, hash one
    # character short -- but the provider id transcribed exactly.
    assert repair_reference(
        "pexels-hands-reading-and-tearing-paper-bin-6670603-7617764",
        APPROVED,
    ) == "candidate-pexels-hands-tearing-blank-paper-at-cafe-ta-6670603-7617764e"


def test_leaves_a_correct_id_untouched():
    known = "candidate-wikimedia-clareen-bus-station-ireland-26498465-12d2b64e"

    assert repair_reference(known, APPROVED) == known


def test_an_invention_is_not_repaired():
    # Numbers matching nothing means the asset was made up, which is a
    # different failure from mistyping one and must still be reported.
    assert repair_reference("pexels-invented-clip-9999999-abcdef01", APPROVED) == ""


def test_an_ambiguous_number_is_not_guessed():
    assert repair_reference("x-123456-y", {"a-123456-b", "c-123456-d"}) == ""


def test_short_numbers_are_not_distinctive_enough():
    # Digits inside a description ("route-66") would match by coincidence.
    assert distinctive_numbers("pexels-route-66-clip-12345") == []


def test_repair_references_reports_what_it_changed():
    resolved, repairs = repair_references(
        [
            "pexels-hands-reading-and-tearing-paper-bin-6670603-7617764",
            "candidate-wikimedia-clareen-bus-station-ireland-26498465-12d2b64e",
            "pexels-invented-9999999-abcdef01",
        ],
        APPROVED,
    )

    assert resolved[0].startswith("candidate-pexels-hands-tearing-blank-paper")
    assert resolved[1] == (
        "candidate-wikimedia-clareen-bus-station-ireland-26498465-12d2b64e"
    )
    # An invention passes through unchanged so the caller still rejects it.
    assert resolved[2] == "pexels-invented-9999999-abcdef01"
    assert len(repairs) == 1
    assert repairs[0][0].startswith("pexels-hands-reading")
    assert repairs[0][1].startswith("candidate-pexels-hands-tearing-blank-paper")


def test_a_number_inside_a_longer_number_is_not_a_match():
    # "667060" appears inside "6670603" but identifies nothing: the digits
    # must stand on their own for the target to be certain.
    assert (
        repair_reference(
            "pexels-clip-667060-deadbeef",
            APPROVED,
        )
        == ""
    )


def test_suffix_repair_resolves_a_mistyped_prefix():
    from tc_acc.identifiers import repair_reference_by_suffix

    known = {
        "episode-792218547084-claim-14",
        "episode-792218547084-claim-3",
    }
    # The shared episode number cannot distinguish claims; the tail can.
    assert (
        repair_reference_by_suffix(
            "holyshistory-792218547084-claim-14", known
        )
        == "episode-792218547084-claim-14"
    )
    # A tail two ids share stays ambiguous.
    assert (
        repair_reference_by_suffix("x-claim-14", {"a-claim-14", "b-claim-14"})
        == ""
    )


def test_label_repair_settles_spelling_but_not_meaning():
    from tc_acc.identifiers import repair_label

    known = {"Harbour Point, Clareen", "Clareen Bus Station"}

    # Casing, punctuation and spacing drift when a model retypes a label.
    assert repair_label("harbour point clareen", known) == "Harbour Point, Clareen"
    assert repair_label("CLAREEN  BUS  STATION", known) == "Clareen Bus Station"
    # A paraphrase is a different label, not a spelling difference.
    assert repair_label("The beach at Harbour Point", known) == ""
    assert repair_label("", known) == ""


def test_label_repair_refuses_an_ambiguous_match():
    from tc_acc.identifiers import repair_label

    # Two labels that normalise identically cannot be told apart.
    assert repair_label("the hotel", {"The Hotel", "the  hotel!"}) == ""


def test_repair_labels_reports_what_it_changed():
    from tc_acc.identifiers import repair_labels

    resolved, repairs = repair_labels(
        ["harbour point clareen", "Clareen Bus Station", "Invented Place"],
        {"Harbour Point, Clareen", "Clareen Bus Station"},
    )

    assert resolved[0] == "Harbour Point, Clareen"
    assert resolved[1] == "Clareen Bus Station"
    # An invention passes through so the caller still rejects it.
    assert resolved[2] == "Invented Place"
    assert repairs == [("harbour point clareen", "Harbour Point, Clareen")]


def test_label_key_preserves_every_script():
    """Stripping non-Latin characters collapsed distinct labels.

    Checked against 3,387 real labels from four runs: the old normalisation
    made "Subject背影" and "Subject" the same key. A wrong label routes an
    asset to the wrong beat, which is a factual error on screen rather than a
    crash, so the normalisation must not delete meaning.
    """
    from tc_acc.identifiers import repair_label

    known = {"Subject背影", "Foreground Rocks"}

    # The bare word must not be repaired into the fuller label.
    assert repair_label("Subject", known) == ""
    # Casing and punctuation are still ignored.
    assert repair_label("foreground rocks", known) == "Foreground Rocks"
    assert repair_label("subject背影", known) == "Subject背影"


def test_label_key_does_not_equate_accented_and_plain_spellings():
    from tc_acc.identifiers import repair_label

    # Dropping an accent is a different word, not a spelling variant we can
    # safely resolve, so it is refused rather than guessed.
    assert repair_label("Cafe Nero", {"Café Nero"}) == ""


def test_label_key_keeps_word_boundaries():
    """Concatenating tokens equated labels that mean different things.

    "Note Book" and "Notebook" collapsed to one key under
    the previous normalisation, so a real label could be repaired into a
    different one -- a wrong asset on a beat, which is a factual error on
    screen rather than a crash.
    """
    from tc_acc.identifiers import repair_label

    assert repair_label("Notebook", {"Note Book"}) == ""
    assert repair_label("Note Book", {"Notebook"}) == ""
    # The repairs this exists for still work.
    assert (
        repair_label("harbour point clareen", {"Harbour Point, Clareen"})
        == "Harbour Point, Clareen"
    )
    assert (
        repair_label("APPROACHING  TRAIN", {"Approaching train"})
        == "Approaching train"
    )


def test_label_repair_absorbs_a_leading_article():
    """A run died on "The Enduring Unknowns" when the plan said "Enduring Unknowns".

    The model restated the label with a definite article. That is a
    restatement, not an invention, and it ended a stage at editorial.
    """
    from tc_acc.identifiers import repair_label

    known = {"Enduring Unknowns", "The Enduring Mystery", "The Autopsy Findings"}
    assert repair_label("The Enduring Unknowns", known) == "Enduring Unknowns"
    # And in the other direction, which is the same restatement.
    assert (
        repair_label("Discovery", {"The Discovery"}) == "The Discovery"
    )


def test_leading_article_is_a_fallback_and_never_redirects_an_exact_match():
    """An exact match must win even when an article-stripped rival exists."""
    from tc_acc.identifiers import repair_label

    known = {"The Discovery", "Discovery"}
    # Each resolves to itself; neither is pulled onto the other.
    assert repair_label("the discovery", known) == "The Discovery"
    assert repair_label("DISCOVERY", known) == "Discovery"


def test_leading_article_repair_refuses_when_it_would_be_ambiguous():
    from tc_acc.identifiers import repair_label

    # Two known labels collapse to the same article-free key, so the intended
    # target is not certain and nothing is repaired.
    assert repair_label("Discovery", {"The Discovery", "A Discovery"}) == ""


def test_article_stripping_does_not_reach_inside_a_label():
    """Only a *leading* article is dropped; one carrying meaning is kept."""
    from tc_acc.identifiers import repair_label

    assert repair_label("Before Storm", {"Before the Storm"}) == ""
    # A label that is only an article keeps it rather than keying to nothing.
    assert repair_label("The", {"A"}) == ""


def test_hash_repair_resolves_a_conflated_web_image_id():
    """The model took the readable half from one id and the hash from another.

    A run asked for
    ``openai_web_image-...-https-news-one-82cc544e``. No such asset existed:
    ``82cc544e`` belongs to the ``archive-a`` asset, while ``news-one``
    belongs to two others. The stage died rather than resolve it.
    """
    from tc_acc.identifiers import repair_reference_by_hash

    known = {
        "candidate-openai_web_image-unnamed-man-case-pictures-https-archive-a-82cc544e",
        "candidate-openai_web_image-unnamed-man-case-pictures-https-news-one-1c0b03bf",
        "candidate-openai_web_image-unnamed-man-case-pictures-https-news-one-7f55b37e",
    }
    asked = "openai_web_image-unnamed-man-case-pictures-https-news-one-82cc544e"

    assert repair_reference_by_hash(asked, known) == (
        "candidate-openai_web_image-unnamed-man-case-pictures-https-archive-a-82cc544e"
    )


def test_hash_repair_refuses_a_tail_short_enough_to_be_ordinary_data():
    """``claim-14`` and ``shot-29`` must never resolve by their trailing token."""
    from tc_acc.identifiers import repair_reference_by_hash

    known = {"episode-792218547084-claim-14", "timeline-shot-29"}

    assert repair_reference_by_hash("some-other-claim-14", known) == ""
    assert repair_reference_by_hash("some-other-shot-29", known) == ""


def test_hash_repair_refuses_a_non_hex_tail():
    """A word is a description, not a hash, and descriptions are what drift."""
    from tc_acc.identifiers import repair_reference_by_hash

    known = {"candidate-pexels-a-quiet-harbour-at-dawn"}

    assert repair_reference_by_hash("candidate-pexels-x-at-dawn", known) == ""


def test_hash_repair_refuses_an_ambiguous_hash():
    from tc_acc.identifiers import repair_reference_by_hash

    known = {"provider-one-82cc544e", "provider-two-82cc544e"}

    assert repair_reference_by_hash("provider-three-82cc544e", known) == ""


def test_hash_repair_leaves_a_genuine_invention_unresolved():
    """A hash matching nothing is an invention, and must still be reported."""
    from tc_acc.identifiers import repair_reference_by_hash

    known = {"candidate-openai_web_image-something-1c0b03bf"}

    assert repair_reference_by_hash("candidate-made-up-deadbeef", known) == ""


def test_hash_repair_is_case_insensitive():
    from tc_acc.identifiers import repair_reference_by_hash

    known = {"candidate-provider-slug-82CC544E"}

    assert (
        repair_reference_by_hash("candidate-other-slug-82cc544e", known)
        == "candidate-provider-slug-82CC544E"
    )


def test_label_repair_strips_a_reviewer_disambiguator():
    """A plan may name two scenes the same; a reviewer referring to them cannot.

    Faced with two "Nothing to Identify Him" scenes, a reviewer wrote
    "Nothing to Identify Him (forensic examination occurrence)". No scene
    carries that name, so the revision was requested for a label nothing could
    match and the router returned neither instance.
    """
    from tc_acc.identifiers import repair_label

    known = {"Nothing to Identify Him", "The Medical Turn"}

    assert (
        repair_label(
            "Nothing to Identify Him (forensic examination occurrence)", known
        )
        == "Nothing to Identify Him"
    )
    assert (
        repair_label(
            "Nothing to Identify Him (first occurrence: no wallet or cards)",
            known,
        )
        == "Nothing to Identify Him"
    )


def test_a_parenthetical_that_is_part_of_the_real_label_is_left_alone():
    """Stripping must not fire when the known label carries the parenthetical."""
    from tc_acc.identifiers import repair_label

    known = {"The Discovery (1993)"}

    assert repair_label("The Discovery (1993)", known) == "The Discovery (1993)"
    # and a different year is a different scene, not a disambiguator to strip
    assert repair_label("The Discovery (1994)", known) == ""


def test_a_disambiguator_matching_nothing_is_still_refused():
    from tc_acc.identifiers import repair_label

    assert repair_label("Some Other Scene (second occurrence)", {"Discovery"}) == ""


def test_a_disambiguator_is_refused_when_the_base_is_ambiguous():
    """Two known labels sharing the stripped form give no certain target."""
    from tc_acc.identifiers import repair_label

    known = {"The Discovery", "Discovery"}

    assert repair_label("Discovery (second occurrence)", known) == "Discovery"


def test_a_truncated_hash_finds_no_match_because_that_boundary_speaks_handles():
    """The truncated-prefix fallback from 17b9348a is gone, on review.

    v2-full8-20260816-01 wrote ``...-cdcad10`` for an id ending ``-cdcad10c``
    and a unique-prefix guess briefly absorbed it here. The refinement
    boundary that produced the truncation now hands the model short
    deterministic handles instead of ids to transcribe (see
    test_asset_refinement_scenes), so the exact-hash contract holds again:
    a hash that matches nothing exactly resolves to nothing.
    """
    from tc_acc.identifiers import repair_reference_by_hash

    known = {
        "candidate-openai_web_image-clareen-hotel-room-705-exterior-https-news-one-cdcad10c",
        "candidate-openai_web_image-clareen-hotel-room-705-exterior-https-news-two-012e3d70",
    }
    assert (
        repair_reference_by_hash(
            "openai_web_image-clareen-hotel-room-705-exterior-https-news-one-cdcad10",
            known,
        )
        == ""
    )
