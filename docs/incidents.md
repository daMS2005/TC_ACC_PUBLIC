# Selected debugging write-ups

The production repository keeps a log of every failure with its root cause, the
fix, and the measurements behind each number — 56 entries at the time of
writing. Four are reproduced here, chosen because the wrong turns are the
interesting part.

---

## A corrupted preview defeated a working reviewer

*Code: `tc_acc/assets/preview.py`*

**Symptom.** An unusable image — a transparent icon on a plain background —
appeared in a finished episode at 1:17, despite a vision model reviewing every
candidate.

**First conclusion, wrong.** I compared the stored preview files and concluded
the asset was never in the candidate pool, and that something downstream had
substituted it.

**What broke it open.** One question: *"how did it make it into the pool
then?"* My answer had assumed the pool and the render drew on the same picture.
They do not. Each asset has a source file used by the renderer and a separate
preview generated for the vision reviewer, and the two can diverge.

**Root cause.** The preview generator flattened transparency onto a default
background. A transparent icon became a plain square. The reviewer approved a
plain square — correctly, given what it was shown — and the renderer then drew
the real file.

**Proof.** Regenerating the preview from the stored source reproduced the stored
square byte-for-byte. Not an inference: the same bytes.

**Fix.** Composite onto an explicit white canvas so the preview matches what the
renderer will draw.

**Verification in production.** On the next full run, 17 of 17 assets of that
class were rejected by the same reviewer that had previously approved them.

**What I got wrong afterwards.** I also added three defensive guards, including
a byte-size floor. The floor false-positived on legitimate flat-colour maps and
scans, and they were removed on instruction — the correct call. The original bug
was already fixed; the guards only made the pipeline more brittle.

---

## A platform rule that fails silently

*Code: `tc_acc/publish.py`*

**Symptom.** Chapter markers were empty in the publishing bundle, beside a
metadata file holding 59 perfectly good chapters.

**First cause.** The metadata stores a chapter's start as a pre-formatted
`"M:SS"` string. The parser only understood a numeric field. It produced empty
output and reported nothing wrong, because the raw list was non-empty. Fixed —
and a chapter list that renders to nothing now counts as missing.

**Second cause, worse.** With parsing fixed, all 59 came through — for a 9:55
episode, with **31 of the 58 gaps under the platform's ten-second minimum**. The
platform does not drop the offending entry. It ignores the entire list,
silently. Pasting that output would have produced no chapters and no error.

**First fix, wrong.** I thinned the list to the 37 entries that satisfied the
spacing rule. That was treating a symptom: those entries are *narration beats*,
and none corresponds to anything the viewer sees.

**Correct fix.** The episode is cut into acts, and only acts that earn an
on-screen act card are marked at all — capped at four. Chapters now derive from
the act structure and the admitted act cards: five entries, matching the cards
the render actually draws.

One detail worth keeping: the times come from the frame index over the canvas
frame rate, not from narration seconds. The frame is the video's own clock, and
the two diverge wherever anything sits between the opening and the body.

**Lesson.** Both bugs were invisible to fixture-based tests and both surfaced
immediately against real production data.

---

## Four wrong diagnoses before the right one

**Symptom.** A video source began returning HTTP 403 on transfer.

**Wrong diagnoses, in order:** stale tooling; the format selector; a difference
between the library and CLI interfaces; a missing JavaScript runtime. Each was
investigated. Each was wrong.

**Root cause.** Per-video rate limiting, triggered by my own repeated test
downloads — roughly twelve of them — against the same source.

**Why it took four attempts.** Small probe requests kept succeeding while full
transfers failed. I let that mislead me twice: a passing probe reads as "access
works, so the problem is local."

**Fix.** Retry with backoff, distinguishing transient refusals (403, 429) from
permanent verdicts (private, unavailable, DRM), which fail immediately. Plus a
memory of refused sources, so siblings are skipped rather than re-attempted.

**Method note.** The decisive evidence came from two probes run side by side: a
control video never touched, and the hammered source. Their disagreement
answered in minutes what four rounds of reasoning had not — the control served
while the hammered source refused, so the limit was per-video, not machine-wide.

---

## A resume that short-circuited its own repair loop

**Symptom.** An editorial stage produced a plan containing a shot with an empty
clip window.

**First conclusion, wrong.** I committed a fix believing the clip-range assigner
had corrupted a good plan. It had not — the asset was in the routed rankings the
whole time. I retracted it.

**Second conclusion, also wrong.** That a zero-length window was itself the
defect. It is not: it is a legitimate intermediate state the repair loop is
expected to resolve.

**Actual cause.** Resume was short-circuiting the repair loop. A target marked
complete in a previous attempt was accepted on resume without re-checking that
its window had ever been filled in, so an unconverged intermediate was treated
as a finished result.

**Fix.** On resume, a completed target whose shot has an empty or inverted
window is stripped back to pending, so the repair loop runs.

**Lesson.** Two retractions in one investigation, with the same root pattern: I
diagnosed from the artifact's *final state* rather than the sequence that
produced it. A zero-length window looks identical whether it is a corruption or
an intermediate — the difference is only visible in the history.
