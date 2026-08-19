# Configuration

`tc_acc.example.json` mirrors the real file's shape — all 12 sections and all
96 keys — with every value replaced by a type marker.

The key names are worth reading: they show what the system considers
configurable, which is most of its behaviour. Canvas geometry, voice provider,
model per stage, retry ceilings, review thresholds and feature gates are all
settings rather than code.

The values are withheld because the values *are* the tuning. Each was set by
measurement across production runs, and several carry a comment in the source
recording the comparison that produced them. A threshold without its
measurement is a number nobody can safely change.
