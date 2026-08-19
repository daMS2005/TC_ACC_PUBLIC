# TC_ACC — an autonomous documentary studio

**Daniel Mora**

A multi-agent system that takes a single case reference and returns a finished
documentary episode — researched, written, narrated, illustrated, cut and
rendered. Twenty-nine stages, six departments, two review gates. No step
requires a person.

![Four frames from an autonomously produced episode](docs/images/episode-stills.jpg)

Four frames from one run: a stock plate, archival CCTV, an archive insert, and
a rendered location map. The system selected, sourced, reviewed and cut all
four.

> **About this repository.** A public excerpt of a private production system.
> The structure mirrors the real repository and the code in it is real,
> unedited production code — but the prompt layer, the tuned configuration and
> the orchestration are withheld, and nothing here runs the pipeline. Each
> package's `__init__.py` says what it holds and what was held back. See
> [NOTICE.md](NOTICE.md).

---

## The central design problem

An LLM pipeline this long fails in one of two ways. Either the model is trusted
with things it cannot guarantee — and the run produces something unrenderable,
or worse, something plausible and false — or the model is constrained so tightly
it produces nothing worth watching.

The whole system is an answer to where that line goes:

> **The model authors editorial decisions. Deterministic code referees them.**

Which image carries a beat, what the opening shows, whether a map belongs —
judgement, and it goes to a language model. Whether a clip window exists inside
a source video, whether a plan can be drawn, whether an asset's dimensions match
the file on disk — arithmetic, enforced in code that cannot be argued with.

The corollary shaped more of this codebase than any other rule:

> **A model failed by machine echo is our bug, not the model's.**

When a model returns a bad answer, the first question is whether it was asked a
fair one. Two examples, both in the code here:

**`tc_acc/handles.py`** — six assets differing only in an eight-character hash
suffix produced mistyped references. The codebase had grown *suffix-repair
logic* to cope with it. The fix deleted that entire failure class: the model is
handed short handles (`a17`) it cannot mistype, answers in handles, and the
deterministic side owns the mapping back to real ids. Handles are transport,
never identity.

**`tc_acc/assets/preview.py`** — an unusable image reached a finished episode
after a vision model approved it. The model was not wrong. It had been shown a
flattened preview in which a transparent icon rendered as a plain white square.
Fixing the *flattening* made the same reviewer reject that class of image **17
times out of 17** on the next production run.

Neither was a prompt-tuning problem. Both would have been misdiagnosed as "the
model is unreliable."

---

## Typed agents, and what happens when one fails

`tc_acc/agents/typed_runtime.py` is the core of the model layer. Every call
declares the output type it must return. The response is validated **before
anything downstream can see it**, and a response that fails its contract is:

1. retried against the contract,
2. failed over to a declared alternative model,
3. escalated as a typed issue.

It is never silently coerced into shape. `validated_graph.py` composes these
into a graph that can repair its own output — the loop that lets a stage recover
from a bad answer without a human, and stops rather than degrading when it
cannot.

**No silent fallbacks.** A speech provider without credit stops the run instead
of narrating in a different voice. Where substitution is permitted, it writes a
finding onto the episode. The failure this prevents is the expensive one: a run
that completes, looks fine, and quietly swapped something that mattered.

**Refusals and answers are different.** An HTTP 403 on a transfer means the
server declined to serve a file it holds — retried with backoff. "Private video"
is an *answer*; retrying returns the same answer more slowly, so it fails
immediately.

---

## Architecture

```
      research  →  story  →  assets  →  sound
                                          │
                            ╔═════════════▼═════════════╗
                            ║  GATE: pre-production      ║
                            ╚═════════════┬═════════════╝
                                          ▼
                                      animation
                                          │
                            ╔═════════════▼═════════════╗
                            ║  GATE: edit                ║
                            ╚═════════════┬═════════════╝
                                          ▼
                                      finishing
```

Stages run as department subgraphs on a LangGraph control plane. The two
showrunner gate stages belong to no department — deliberately. A gate reporting
to a department would be reviewing its own work.

**The stage contract** (`tc_acc/studio/stages.py`) is the system's centre of
gravity. Each stage declares its dependencies, the state it may read and the
state it is *permitted to mutate*, the artifacts it must produce, the config
keys and source paths that invalidate its cached result, and the services it
needs. Because the graph is declared rather than implied by call order, the
control plane can answer questions about a run without executing it — and the
declaration is enforced: a stage that mutates state outside its permitted set
fails.

**Failure is data** (`tc_acc/workflow_contracts.py`). Stages write to a typed
issue ledger — ten categories, three severities, an
`open → routed → addressed → resolved` lifecycle — rather than raising. A
blocking issue stops the run; anything else travels with the episode into the
production report, so a finished video can be interrogated afterwards.

**Resume is first-class.** Stages cost money, so reuse is decided at three
levels: a strict fingerprint check, a semantic check for inputs that changed
without changing meaning, and an arbiter that records *why* a stage is being
rebuilt. A rebuild with no recorded reason is treated as a defect.

**Full detail:** [docs/architecture.md](docs/architecture.md)

---

## Results

| | |
|---|---|
| Latest episode | 9 min 55 s, 1920×1080, 14,294 frames |
| Narration | 8 min 51 s generated speech, 1,289 words |
| Shots | 128 planned, 150 timed cues |
| Assets machine-reviewed | 760 candidates |
| Human input | one case reference |
| Implementation | ~124,000 lines (Python, TypeScript) |
| Tests | 2,657, gating every paid API call |

Timing runs one way: narration is recorded and **measured** before any picture
work, and every later timing derives from that measurement. An earlier design
estimated durations from word counts and reconciled afterwards — it produced
drift that was hard to locate, because by the time it was visible it had been
spread across a hundred shots.

---

## Running the included tests

The pipeline does not run from this repository. The included modules and their
real tests do:

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.12+
pip install pytest pydantic
pytest
```

```
46 passed
```

Verified in a clean 3.12 environment with no copy of the private package
present. Python 3.12 is required — the code uses `datetime.UTC`.

---

## Layout

**Bold** entries contain real code.

```
tc_acc/
├── agents/
│   ├── typed_runtime.py    ** typed model calls, validation, failover
│   └── validated_graph.py  ** self-repairing agent graph
├── handles.py              ** short model-safe ids
├── models.py               ** the domain model
├── workflow_contracts.py   *  excerpt: the issue-ledger vocabulary
├── editorial_contracts.py  ** editorial output contracts
├── studio/stages.py        *  excerpt: stage contract + 3 of 29 stages
├── assets/preview.py       ** the review-preview generator
├── publish.py              ** collecting a finished episode for upload
├── storage.py utils.py identifiers.py coercion.py
│   chapter_timecode.py media_provenance.py                    ** real
├── animation/ brand/ prompts/ providers/ search/    withheld
tests/                      ** the real tests — they pass as published
config/                     all 96 key names, values redacted
docs/                       architecture · practices · incident write-ups
remotion/src/lib/media-fit.ts ** one renderer module; the rest withheld
```

---

## Engineering practices

Ten rules, each traceable to a specific failure — measurement over opinion,
thresholds that carry the measurement that set them, comments that cite the
incident, tests that assert behaviour and never source text, and verification
that reads pixels rather than file metadata.

**[docs/engineering-practices.md](docs/engineering-practices.md)**

Four debugging write-ups, false starts included — including one where I was
wrong four times in a row, and one where two public retractions shared the same
root cause.

**[docs/incidents.md](docs/incidents.md)**

---

## Technology

**Python 3.12** · **TypeScript** · **LangGraph** · **Pydantic** ·
**Remotion** · **ffmpeg** · **pytest** · GitHub Actions

Integrated against OpenAI, Google Gemini, ElevenLabs, Fish Audio, Pexels,
Pixabay, SerpApi and Geoapify — each behind a typed contract with its own retry
and failover behaviour. CI runs the full suite on every push with all provider
credentials blanked, so a green run proves the tree rather than the credentials.
