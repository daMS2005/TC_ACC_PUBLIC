# Architecture

## The shape of the system

Twenty-nine stages, grouped into six departments, running as subgraphs on a
LangGraph control plane. Two review gates sit between the departments, where a
showrunner stage inspects the accumulated work and decides whether the run
continues.

```
                    ┌──────────────────┐
                    │     research     │  5 stages
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │      story       │  4 stages   ← narration recorded here
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │      assets      │  8 stages
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │      sound       │  1 stage
                    └────────┬─────────┘
                             ▼
              ╔══════════════════════════════╗
              ║   GATE: pre-production        ║
              ╚══════════════┬═══════════════╝
                             ▼
                    ┌──────────────────┐
                    │    animation     │  2 stages
                    └────────┬─────────┘
                             ▼
              ╔══════════════════════════════╗
              ║   GATE: edit                  ║
              ╚══════════════┬═══════════════╝
                             ▼
                    ┌──────────────────┐
                    │    finishing     │  7 stages
                    └──────────────────┘
```

The two gate stages belong to no department. A gate that reported to a
department would be reviewing its own work.

## The stage contract

See `tc_acc/studio/stages.py` for the real definition. Each stage declares:

| Field | Declares |
|---|---|
| `dependencies` | which stages must have completed first |
| `state_inputs` / `state_outputs` | which workflow-state fields it reads and writes |
| `permitted_state_mutations` | what it is *allowed* to change — anything else is a defect |
| `artifact_outputs` | the files it must produce |
| `setting_fields` | which config keys change its behaviour |
| `source_fingerprint_paths` | which source files, if edited, invalidate its result |
| `provider_requirements` | which external services it needs |
| `coordination_gates` | which review gate it answers to |
| `contract_version` | bumped when the stage's meaning changes |
| `applicability` | whether it always runs, or only under some condition |

Because the graph is **declared** rather than implied by call order, the control
plane can answer questions about a run without executing it: what a stage will
touch, whether its inputs have changed, whether a stored result is still valid,
and which services a run needs before it starts.

The declaration is enforced, not documentation. A stage that mutates state
outside `permitted_state_mutations` fails.

## Four kinds of stage

| Kind | Count | What it is |
|---|---|---|
| workflow | 8 | multi-step lanes with internal retry and repair loops |
| tool worker | 9 | deterministic work against an external tool |
| model agent | 8 | a single typed model call with a validated output contract |
| deterministic | 4 | pure computation; no model, no network |

The split governs cost and trust. A deterministic stage produces the same answer
every time and can be re-run freely. A model agent cannot, so its output is
contract-validated before anything downstream is allowed to see it.

## Ordering: narration before picture

Narration is recorded and **measured** in the story department, before any
picture work begins. Every later timing — shot lengths, the animation plan, the
total frame count — derives from that measured duration.

An earlier design estimated durations from word counts and reconciled
afterwards. It produced timing drift that was hard to locate, because by the
time a discrepancy was visible it had been distributed across a hundred shots.
Measuring first means the picture is cut to the audio that actually exists.

## Resume, and semantic reuse

Stages cost money, so a run that fails at stage 20 resumes at stage 20. Reuse is
decided at three levels:

**Strict.** A stored result is reused only if the stage completed, the contract
version still matches, the input fingerprint is unchanged, every declared output
path still exists, and the artifacts hash to what they hashed to before.

**Semantic.** Some inputs change without changing meaning. A stage may declare
inputs as excluded from its fingerprint, so a cosmetic upstream change does not
force expensive re-work downstream.

**The arbiter.** A separate decision records *why* a stage is being rebuilt. A
rebuild without a recorded reason is treated as a defect, not a convenience.

The fingerprint covers declared state inputs, the relevant config keys, and the
listed source files — so editing a stage's source invalidates that stage, and a
live run fingerprints the tree it is running against.

## Failure is data, not an exception

See `tc_acc/workflow_contracts.py`. Stages write to a structured ledger rather
than raising:

```
category   technical_invalid · provider_unavailable · quality_below_floor
           missing_evidence · contradictory_evidence · missing_visual_coverage
           performance_failure · creative_dead_end · no_progress · policy_block

severity   info · warning · blocking

status     open → routed → addressed → resolved
```

A blocking issue stops the run. Anything else travels with the episode into the
production report, so a finished video can be interrogated afterwards — what was
missing, what was substituted, what the gate allowed through.

This is why roughly a fifth of the implementation is repair, resume and reuse
machinery. A pipeline that refuses rather than degrades, and repairs rather than
restarts, is substantially larger than one that does neither — a deliberate
trade, not accidental growth.

## Evidence discipline

Research produces a **claim ledger**: the set of assertions the episode is
permitted to make, each tied to its sources. The script is written against that
ledger, and a later pass may edit the writing for flow but may not change a
claim. The distinction is enforced rather than trusted.

This matters for the subject matter. The episodes concern real unsolved cases
and real people, and the difference between "the evidence supports this" and
"this reads well" is the difference between a documentary and a fabrication.
