# Tests

The full suite runs as a preflight gate before any paid API call — with
provider credentials blanked, so a green preflight proves the tree rather than
the credentials.

The files here are the real tests for the modules included in this
excerpt, and **they pass against the code as published**:

    $ python -m pytest tests/ -q
    46 passed

Two tests were removed rather than left failing, because they exercise modules
that are withheld: one covering the CLI entry point, and one file whose fixtures
import the workflow-state package. Nothing else was edited.

## What to look for

**Tests assert behaviour, never source text.** Asserting on source is banned
across the suite. A test that reads implementation passes for the wrong reason
and blocks the refactor it should have protected.

**A test that exists because something failed records what failed**, with the
date, so the reason survives independently of whoever remembers it:

    def test_chapters_written_as_timecode_strings_are_read(tmp_path):
        """Reading only the numeric form produced an empty chapters.txt beside
        a metadata package holding fifty-nine good chapters (2026-08-18).
        """

**Names state the behaviour**, not the function under test:

    test_a_missing_piece_is_recorded_rather_than_invented
    test_a_running_run_is_left_alone
    test_intermediates_are_kept_when_no_final_video_exists
    test_chapters_come_from_the_acts_the_viewer_can_see

**The guards get the most coverage.** `reclaim_space` deletes files, so the
tests that matter most assert what it must *not* delete: a job still running,
and a directory with no finished render.

**Fixtures build the real directory layout** rather than mocking the
filesystem, so a failure means the shape on disk changed — which is the thing
worth being told about.
