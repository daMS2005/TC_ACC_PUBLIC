# Engineering practices

Every rule here exists because something failed. They are enforced by tests and
review, not aspirational.

## 1. The model decides editorially; code decides what is renderable

Which image carries a beat, what the opening shows, whether a map belongs —
judgement calls, and they go to a language model.

Whether a clip window exists inside a source video, whether a plan can be drawn
at all, whether an asset's dimensions match the file on disk — arithmetic, and
it is enforced in deterministic code.

The boundary is the design. Blurring it in either direction produces a system
that is either unable to make a creative choice or unable to guarantee it can
render one.

## 2. A bad model answer is first suspected to be a bad question

See `tc_acc/handles.py` for the canonical example: six assets differing only in
an eight-character hash suffix produced a mistyped reference, and the codebase
had grown suffix-repair logic to cope. The fix was to hand the model handles it
could not mistype.

See `tc_acc/assets/preview.py` for the second: a vision model approved an
unusable image because it was shown a corrupted rendering of it. Correcting the
rendering made the same reviewer reject that class of image every time.

Both would have read as "the model is unreliable" under a different diagnosis.
Neither was.

## 3. Stages refuse rather than substitute

A speech provider without credit stops the run instead of narrating in a
different voice. Archival footage that cannot be fetched is recorded as
unavailable rather than replaced with stock. Where substitution is permitted, it
writes a finding onto the episode.

The failure this prevents is the expensive one: a run that completes and looks
fine, having quietly swapped something that mattered.

## 4. Retries distinguish a refusal from an answer

An HTTP 403 on a video transfer means the server declined to serve a file it
holds. That is a refusal, and it is retried with backoff.

"Private video" and "DRM protected" are *answers*. Retrying returns the same
answer more slowly, so those fail immediately.

## 5. Every threshold carries the measurement that produced it

A tolerance cites the comparison that set it. A word budget cites the measured
speech rate of the voice it was derived from, and notes that changing voices
invalidates it.

One tolerance was recalibrated after measuring that an image provider quantises
output to a 32-pixel grid, so a 640×480 request returns 1184×864 — a 3% aspect
drift that is the provider's geometry, not a defect.

A constant without its measurement is a number nobody can safely change,
because nobody knows what it was protecting.

## 6. Comments explain why, and cite the incident

Comments do not restate the code. They record the decision and what would
happen if it were reversed — with a date where one exists, so the reasoning
survives the people who remember it.

## 7. Tests assert behaviour, never source text

Asserting on source is banned. A test that reads implementation passes for the
wrong reason and blocks the refactor it should have protected.

## 8. Verify frames, not files

A video file can have the correct duration, frame count, codec and size and
still show the wrong thing. Checks examine pixels. Learned from a render that
passed every property check and was visibly broken.

## 9. Measurement outranks opinion

Disagreements are settled by measuring. Several conclusions here were reversed
by measurement, including two diagnoses that were stated and then retracted when
the evidence did not support them.

A related discipline: a long test run is only meaningful against the tree it ran
on. If the working tree moved during the run, the result is void — not a bug to
investigate.

## 10. Concurrency rules exist because of a specific loss

Multiple agent sessions and pipeline runs share one machine. The rules — work in
your own checkout, never rewrite shared state, commit early, never move the
repository head while a suite or render is running — come from an incident in
which a routine command discarded roughly 2,600 lines of uncommitted work while
a second session was spending its test results on a tree that no longer existed.

Neither session did anything unusual. The shared state is what made both
failures possible.
