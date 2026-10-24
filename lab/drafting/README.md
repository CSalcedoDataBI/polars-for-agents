# Drafting lab

Hand-run tooling that drafts the trap notes in `skills/polars-reference/notes/`. It is not part of
the plugin and it is not run by CI, because it spends API credit.

| Step | Script | What it guarantees |
|---|---|---|
| 1. Draft | `draft.py` | per chunk of a catalogue group, Claude writes trap notes using only catalogue names; each name is checked with `scripts/catalog_names.py` and each example is run on the installed polars, its stdout kept; failures go back once for repair |
| 2. Verify | `verify.py` | a fresh call reads each passing note next to its real output and the docstrings it cites, and keeps, fixes or drops it |
| 3. Promote | `promote.py` | the surviving notes become one Markdown file per group, name-checked again; CI checks them on every PR |

Everything the calls returned is in `out/<chunk>.json` (passed, failed with the reason, and the
verifier's verdicts). `out/ledger.jsonl` records the cost of every call; both scripts stop before
their `--budget` cap would be crossed, and refuse to call after the promotional credit's end date.
