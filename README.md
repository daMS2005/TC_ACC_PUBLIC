# TC_ACC

An autonomous documentary studio. Give it a link to an unsolved case and it
returns a finished ten-minute episode about two hours later — researched,
written, narrated, illustrated, cut, rendered, and packaged with a thumbnail
and description ready to upload. No human step in between.

![Four frames from an autonomously produced episode](docs/images/episode-stills.jpg)

Four frames from a single run: a stock coastal plate, archival CCTV of the case
subject, an archive insert, and a location map rendered by the pipeline. All
four were found, vetted and cut automatically.

> A public excerpt of a private repository. Same structure, real code, but the
> prompts, the tuned configuration and the orchestration are not included and
> it will not run a pipeline. [NOTICE.md](NOTICE.md) lists what is missing and
> why.

**Latest run:** 9:55 · 1920×1080 · 14,294 frames · 128 shots · 760 assets
machine-reviewed · one case link as input.

---

# Architecture

Twenty-nine stages, six departments, two review gates. The structure is modelled
on a production company, and the division of labour is load-bearing rather than
decorative.

```
  ┌─ RESEARCH ────────────────────────────────────────────────────────┐
  │  0  source_intake             the case link                       │
  │  1  research_collection       bounded search: web, wiki, video     │
  │  2  case_media                transcripts, archival video, clips   │
  │  3  evidence_synthesis        the dossier + the claim ledger       │
  │  4  case_media_viability      is there enough material to film?    │
  └───────────────────────────────┬───────────────────────────────────┘
                                  │  claim ledger
  ┌─ STORY ───────────────────────▼───────────────────────────────────┐
  │  5  story_development         timeline, sensitivity review        │
  │  6  script                    written against the ledger only     │
  │  7  narrator                  flow edits; may not change a claim  │
  │  8  voice                     ★ narration recorded and measured   │
  └───────────────────────────────┬───────────────────────────────────┘
                                  │  measured audio → every later timing
  ┌─ ASSETS ──────────────────────▼───────────────────────────────────┐
  │  9  creative_direction        what the episode needs to show      │
  │ 10  asset_planning            the shot list                       │
  │ 11  asset_acquisition         stock, web images, archival video   │
  │ 12  map_production            rendered location maps              │
  │ 13  asset_validation          a vision model reviews every one    │
  │ 14  case_media_reconciliation predicted supply vs what arrived    │
  │ 15  asset_upscale             enhancement, behind a gate          │
  │ 16  information_flow          what the viewer knows, and when     │
  └───────────────────────────────┬───────────────────────────────────┘
  ┌─ SOUND ───────────────────────▼───────────────────────────────────┐
  │ 17  sound_design              beds and accents                    │
  └───────────────────────────────┬───────────────────────────────────┘
                                  ▼
        ╔═══════════════════════════════════════════════════════╗
        ║  18  showrunner_preproduction        ── REVIEW GATE ── ║
        ║      reads everything above, decides whether to go on  ║
        ╚═══════════════════════════┬═══════════════════════════╝
  ┌─ ANIMATION ───────────────────────▼───────────────────────────────┐
  │ 19  editorial                 shot selection and repair           │
  │ 20  video_enhancement         motion and framing                  │
  └───────────────────────────────┬───────────────────────────────────┘
                                  ▼
        ╔═══════════════════════════════════════════════════════╗
        ║  21  showrunner_edit                 ── REVIEW GATE ── ║
        ╚═══════════════════════════┬═══════════════════════════╝
  ┌─ FINISHING ───────────────────────▼───────────────────────────────┐
  │ 22  brand_structure           chapters and act structure          │
  │ 23  brand_geometry            where things sit in frame           │
  │ 24  brand_treatment           the archive visual grammar          │
  │ 25  render                    Remotion draws the frames           │
  │ 26  metadata                  titles, description, chapters       │
  │ 27  episode_thumbnail         the poster                          │
  │ 28  delivery                  packaging                           │
  └───────────────────────────────────────────────────────────────────┘
```

Stages run as department subgraphs on a LangGraph control plane.

## The review gates sit outside the departments

Stages 18 and 21 belong to no department. A gate that reported to one would be
reviewing its own work.

The pre-production gate reads everything research, story, assets and sound
produced and decides whether the run continues. It exists to catch the failure
where every individual stage succeeded but the episode does not hold together —
nine stages can each report green and still produce an episode with no usable
footage for its second act. That class of problem is invisible from inside any
one department.

## Narration is recorded before any picture work

Stage 8 sits ahead of every asset, shot and frame. The audio is recorded *and
measured*, and all later timing derives from that measurement: shot lengths,
the animation plan, the total frame count.

The alternative — estimating durations from word counts and reconciling
afterwards — produces drift that is expensive to locate, because by the time it
is visible it has been distributed across a hundred shots. Recording first means
the picture is cut to audio that already exists.

## The stage contract

A stage declares what it will touch before it runs. Each carries a typed
definition ([`tc_acc/studio/stages.py`](tc_acc/studio/stages.py)):

```python
_stage(
    "asset_validation",
    StageKind.DETERMINISTIC_STAGE,
    Department.ASSETS,
    dependencies=("map_production",),
    state_inputs=("asset_manifest",),
    permitted_state_mutations=("asset_manifest",),   # anything else is a defect
    artifact_outputs=("asset_visual_validation",),
    setting_fields=("vision_model", "asset_review_floor"),
    source_fingerprint_paths=("tc_acc/assets/review.py",),
    provider_requirements=(Provider.VISION,),
    coordination_gates=(ReviewGate.PREPRODUCTION,),
)
```

Because the graph is declared rather than implied by call order, the control
plane can answer questions about a run without executing it:

- which external services will this run need, before spending anything
- has anything this stage depends on actually changed
- is last run's cached result still valid
- what is this stage permitted to modify

The declaration is enforced rather than documentary. A stage that mutates state
outside `permitted_state_mutations` fails. `source_fingerprint_paths` means
editing a stage's source invalidates that stage's cache, so a running pipeline
fingerprints the tree it is running on.

## Four kinds of stage

| kind | count | |
|---|---|---|
| `deterministic` | 4 | pure computation; same answer every time, free to re-run |
| `tool_worker` | 9 | ffmpeg, Remotion, the map renderer |
| `model_agent` | 8 | one typed model call, output validated before use |
| `workflow` | 8 | multi-step lanes with their own retry and repair loops |

The split is about cost and trust. A deterministic stage can be redone freely.
A model agent cannot, so its output is contract-validated before anything
downstream is allowed to consume it.

## Resume

Stages cost money, so a run that fails at stage 20 resumes at stage 20. Reuse is
decided at three levels:

**Strict** — reuse only if the stage completed, the contract version matches,
the input fingerprint is unchanged, every declared output still exists, and the
artifacts still hash to their previous values.

**Semantic** — some inputs change without changing meaning. A stage can declare
inputs as excluded from its fingerprint, so a cosmetic upstream edit does not
force expensive downstream re-work.

**The arbiter** — records why a rebuild is happening. A rebuild with no recorded
reason is treated as a defect. This surfaced a real bug: resume was accepting a
stage marked complete whose repair loop had never converged.

## Failure is data, not an exception

Stages write to a typed ledger
([`tc_acc/workflow_contracts.py`](tc_acc/workflow_contracts.py)) rather than
raising:

```
category  technical_invalid · provider_unavailable · quality_below_floor
          missing_evidence · contradictory_evidence · missing_visual_coverage
          performance_failure · creative_dead_end · no_progress · policy_block

severity  info · warning · blocking

status    open → routed → addressed → resolved
```

A blocking issue stops the run. Everything else travels with the episode into
the production report, so a finished video can be interrogated afterwards: what
was missing, what was substituted, what the gate allowed through.

Roughly a fifth of the codebase is repair and resume machinery. A pipeline that
refuses rather than degrades, and repairs rather than restarts, is larger than
one that does neither.

---

# Design principles

**The model makes editorial decisions; deterministic code referees them.**
Which image carries a beat, what the opening shows, whether a map belongs —
judgement, handled by a language model. Whether a clip window exists inside a
source video, whether a plan can be drawn — arithmetic, enforced in code.

**A bad model answer is first treated as a bad question.** Two examples, both
included here:

- [`tc_acc/handles.py`](tc_acc/handles.py) — six assets whose ids differed only
  by an eight-character hash suffix produced mistyped model references, and the
  codebase had grown suffix-repair logic to compensate. Handing the model short
  handles (`a17`) it cannot mistype removed the failure class outright. Handles
  are transport; real ids never leave the deterministic side.
- [`tc_acc/assets/preview.py`](tc_acc/assets/preview.py) — an unusable image
  reached a finished episode after a vision model approved it. The model had
  been shown a flattened preview in which a transparent icon rendered as a plain
  white square. Correcting the flattening caused the same reviewer to reject
  that class of image 17 times out of 17 on the next run.

**Typed agents, no silent coercion.**
[`tc_acc/agents/typed_runtime.py`](tc_acc/agents/typed_runtime.py) runs every
model call against a declared output type. A response that fails its contract is
retried against the contract, failed over to a declared alternative model, then
escalated as a typed issue.

**No silent fallbacks.** A voice provider out of credit stops the run rather
than narrating in a different voice. Where substitution is permitted, it writes
a finding onto the episode.

**Refusals and answers are different.** An HTTP 403 on a transfer means the
server declined to serve a file it holds, and is retried with backoff. "Private
video" is an answer — retrying returns it more slowly — so that fails
immediately.

---

# What is in this repository

Bold entries are real production code.

```
tc_acc/
├── agents/
│   ├── typed_runtime.py    ** typed model calls, validation, failover
│   └── validated_graph.py  ** self-repairing agent graph
├── handles.py              ** short ids a model cannot mistype
├── models.py               ** the domain model
├── editorial_contracts.py  ** editorial output contracts
├── workflow_contracts.py   *  excerpt — the issue ledger
├── studio/stages.py        *  excerpt — stage contract + 3 of 29 stages
├── assets/preview.py       ** the review-preview generator
├── publish.py              ** packaging a finished episode
├── storage.py utils.py identifiers.py coercion.py
│   chapter_timecode.py media_provenance.py            ** real
└── animation/ brand/ prompts/ providers/ search/         withheld

tests/                      ** the real tests for the modules above
config/                     all 96 key names, values redacted
docs/                       architecture, practices, incident write-ups
remotion/src/lib/media-fit.ts  ** one renderer module
```

## Running the tests

The pipeline does not run from this repository. The included modules and their
tests do:

```bash
python -m venv .venv && source .venv/bin/activate   # 3.12+, uses datetime.UTC
pip install pytest pydantic
pytest
```

```
46 passed
```

Verified in a clean 3.12 environment with no copy of the private package on the
path.

## Further reading

- [docs/architecture.md](docs/architecture.md) — the long form of the above
- [docs/engineering-practices.md](docs/engineering-practices.md) — ten rules,
  each traceable to a specific failure
- [docs/incidents.md](docs/incidents.md) — four debugging write-ups: root cause,
  fix, and the measurement that confirmed it

---

Built with Python 3.12, TypeScript, LangGraph, Pydantic, Remotion, ffmpeg and
pytest, against OpenAI, Gemini, ElevenLabs, Fish Audio, Pexels, Pixabay,
SerpApi and Geoapify. CI runs the full suite on every push with every provider
key blanked, so a green run proves the tree rather than the credentials.

No licence is granted. All rights reserved.
