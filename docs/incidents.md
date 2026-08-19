# Incident write-ups

The production repository keeps a log of every failure with its root cause, the
fix, and the measurements behind each number — 56 entries at the time of
writing. Four are reproduced here. The discarded diagnoses are included, because
in each case the wrong answer is what explains the shape of the right one.

---

## A corrupted preview defeated a working reviewer

*Code: [`tc_acc/assets/preview.py`](../tc_acc/assets/preview.py)*

**Symptom.** An unusable image — a transparent icon on a plain background —
appeared in a finished episode at 1:17, despite a vision model reviewing every
candidate.

**Discarded diagnosis.** Comparing the stored preview files suggested the asset
had never been in the candidate pool, and that something downstream had
substituted it. That reading assumed the pool and the render draw on the same
picture. They do not: each asset has a source file used by the renderer and a
separate preview generated for the vision reviewer, and the two can diverge.

**Root cause.** The preview generator flattened transparency onto a default
background, turning a transparent icon into a plain square. The reviewer
approved a plain square — correctly, given what it was shown — and the renderer
then drew the real file.

**Proof.** Regenerating the preview from the stored source reproduced the stored
square byte for byte.

**Fix.** Composite onto an explicit white canvas, so the preview matches what
the renderer will draw.

**Verification.** On the next full production run, 17 of 17 assets of that class
were rejected by the same reviewer that had previously approved them.

**Follow-up that was reverted.** Three defensive guards were added alongside the
fix, including a byte-size floor. The floor false-positived on legitimate
flat-colour maps and scans and was removed. The underlying bug was already
fixed; the guards only added brittleness.

---

## A platform rule that fails silently

*Code: [`tc_acc/publish.py`](../tc_acc/publish.py)*

**Symptom.** Chapter markers were empty in the publishing bundle, beside a
metadata file holding 59 valid chapters.

**First cause.** The metadata stores a chapter's start as a pre-formatted
`"M:SS"` string; the parser only understood a numeric field. It produced empty
output and reported nothing missing, because the raw list was non-empty. A
chapter list that renders to nothing now counts as missing.

**Second cause.** With parsing fixed, all 59 came through — for a 9:55 episode,
with 31 of the 58 gaps under the platform's ten-second minimum. The platform
does not drop the offending entry; it ignores the entire list, with no error.
Publishing that output would have produced no chapters at all.

**Discarded fix.** Thinning the list to the 37 entries that satisfied the
spacing rule. This treated the symptom: those entries are narration beats, and
none corresponds to anything the viewer sees.

**Fix.** The episode is cut into acts, and only acts that earn an on-screen act
card are marked at all — capped at four. Chapters now derive from the act
structure and the admitted act cards: five entries, matching the cards the
render actually draws.

Timecodes come from the frame index over the canvas frame rate rather than from
narration seconds. The frame is the video's own clock, and the two diverge
wherever anything sits between the opening and the body.

**Note.** Both faults were invisible to fixture-based tests and both surfaced
immediately against real production data.

---

## Four discarded diagnoses before the cause

**Symptom.** A video source began returning HTTP 403 on transfer.

**Discarded diagnoses, in order:** stale tooling; the format selector; a
difference between the library and CLI interfaces; a missing JavaScript runtime.
Each was investigated and eliminated.

**Root cause.** Per-video rate limiting, triggered by roughly twelve repeated
test downloads against the same source during debugging.

**Why it took four attempts.** Small probe requests continued to succeed while
full transfers failed. A passing probe reads as "access works, so the problem is
local", which pointed the investigation at the client four times running.

**Fix.** Retry with backoff, distinguishing transient refusals (403, 429) from
permanent verdicts (private, unavailable, DRM), which fail immediately. A memory
of refused sources skips siblings rather than re-attempting them.

**Method.** The decisive evidence came from two probes run side by side: a
control video never previously touched, and the rate-limited source. The control
served while the other refused, establishing that the limit was per-video rather
than machine-wide — a distinction four rounds of reasoning had not settled.

---

## A resume that short-circuited its own repair loop

**Symptom.** An editorial stage produced a plan containing a shot with an empty
clip window.

**First discarded diagnosis.** That the clip-range assigner had corrupted a
valid plan. It had not — the asset was present in the routed rankings
throughout.

**Second discarded diagnosis.** That a zero-length window was itself the defect.
It is a legitimate intermediate state that the repair loop is expected to
resolve.

**Root cause.** Resume was short-circuiting the repair loop. A target marked
complete in a previous attempt was accepted without re-checking that its window
had ever been filled, so an unconverged intermediate was treated as a finished
result.

**Fix.** On resume, a completed target whose shot has an empty or inverted
window is returned to pending, so the repair loop runs.

**Pattern.** Both discarded diagnoses read the artifact's final state rather
than the sequence that produced it. A zero-length window looks identical whether
it is a corruption or an intermediate; only the history distinguishes them. This
is the reasoning behind the rule that a rebuild must record why it is happening.
