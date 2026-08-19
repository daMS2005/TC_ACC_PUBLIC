# Renderer

The episode is drawn by a Remotion composition in TypeScript — ~146 files of
components, compositions and layout maths, driven entirely by the animation
plan the Python side produces.

Only `src/lib/media-fit.ts` is included. Its header explains a decision worth
seeing: it imports nothing, deliberately, so the geometry that decides where a
picture lands on the canvas can be executed under node by the Python test suite
rather than asserted on as source text.

The rest is withheld. The renderer and the motion vocabulary in
`tc_acc/animation/` are two halves of one design and neither reads usefully
without the other.

One property worth stating, because it shaped the Python side: the renderer is
a subprocess that consumes a plan and emits frames. It makes no decisions. If a
shot cannot be drawn, that is a defect in the plan — and the plan is validated
before the renderer is ever started.
