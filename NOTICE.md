# What this repository is, and what it omits

A public excerpt of a private production system. The directory structure
mirrors the real repository and the code in it is real production code, copied
rather than written for display.

Two files were edited, and only in one respect: `tc_acc/identifiers.py` and
`tests/test_identifiers.py` carry fixture strings drawn from a real episode,
which named the case subject, the locations and the channel. Those names were
substituted for invented equivalents. The logic, structure and comments are
untouched, and the tests still pass. Nothing else in this repository was
altered. It is deliberately **not** a working copy: there is no entry
point, no dependency manifest, no environment template, and most modules are
absent. Imports in the included files point at modules that are not here.

Each package's `__init__.py` states what it holds and what was withheld.

## Withheld

| | Why |
|---|---|
| `prompts/` | The prompt text is the most transferable asset here. How a model is asked is most of what separates a usable answer from a plausible one. |
| `config/` values | ~96 keys whose values were set by measurement across production runs. The values *are* the tuning. |
| `studio/` control plane | Orchestration, department subgraphs, resume and reuse machinery. Described in the docs; not reproduced. |
| `animation/`, `brand/` | The editorial and motion vocabulary that gives the output its look. |
| `providers/` | Retry ladders, failover order and output contracts per service. |
| `agents/` (most of) | Two modules are included — the typed-agent runtime and the validated graph. The prompts they send and the per-stage contracts they validate against are withheld. |
| `search/` | Research and evidence collection. |
| `remotion/` (most of) | The TypeScript renderer. One module is included: `src/lib/media-fit.ts`. |

## Included

- Thirteen real Python modules and one TypeScript module, chosen for craft
  and low disclosure risk
- Two excerpts (`stages.py`, `workflow_contracts.py`) showing the contracts that
  shape the system, with the bulk elided and marked
- The real tests for the included modules — they pass as published (46)
- The config's full key structure with every value replaced by a type marker
- Architecture — written for this repository rather than copied, so no
  configured value or prompt text appears by accident

---

No licence is granted. All rights reserved.
