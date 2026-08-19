"""The prompt layer (withheld from this public excerpt).

Pure builders: a prompt module takes typed inputs and returns a string. It
imports nothing from production code, which is enforced by a test -- so a
prompt can never reach for a provider, a file, or a piece of run state.

Each stage resolves its prompt through a show profile, so the same pipeline
can produce a different programme without a code change.

The prompt text itself is the most transferable asset in this system and is
not published. How a model is asked is most of what separates a usable answer
from a plausible one.
"""
