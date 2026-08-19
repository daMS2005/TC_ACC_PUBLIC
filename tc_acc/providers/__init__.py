"""Provider integrations (withheld).

One module per external service, each behind a typed output contract with
its own retry ladder and failover order.

The rule they share: a refusal is retried, an answer is not. An HTTP 403 on a
transfer means the server declined to serve a file it holds, and is retried
with backoff. 'Private video' is an answer -- retrying returns the same answer
more slowly, so it fails immediately.
"""
