"""Typed model calls, output contracts, validation and failover.

Two modules are included here, because they are the part of this system most
worth reading:

``typed_runtime.py`` runs a model call against a declared output type. The
result is validated before anything downstream sees it; a response that does
not satisfy the contract is retried against the contract, then failed over to
a declared alternative model, then escalated. It is never silently coerced
into shape.

``validated_graph.py`` composes those calls into a graph that can repair its
own output — the loop that lets a stage recover from a bad answer without a
human, and that stops rather than degrading when it cannot.

The prompts these agents send, and the per-stage contracts they validate
against, are withheld.
"""
