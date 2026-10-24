"""Regression test for the drafting validator's exception-claim rule.

A note that shows a failing call by catching it and printing `type(e).__name__` is claiming the
call raises; if the run produces no exception name in its output, the example proves the opposite
of its trap and must be dropped. Pure helpers, no polars needed (stdlib only); the Validate
workflow runs it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "lab" / "drafting"))
import draft  # noqa: E402  (imports catalog_names via its own sys.path insert)

# A try/except that prints the caught exception type is an error claim.
assert draft.example_expects_exception(
    "try:\n    df.x()\nexcept Exception as e:\n    print(type(e).__name__)\n"
), "type(e).__name__ idiom should count as expecting an exception"
assert not draft.example_expects_exception("print(df.head())\n"), "no except, no claim"

# The run must actually show an exception name for the claim to hold.
assert draft.output_shows_exception("ComputeError"), "polars error class"
assert draft.output_shows_exception("ValueError: out of range"), "builtin error"
assert not draft.output_shows_exception("shape: (2, 2)\n| a | b |"), "a plain table is not an exception"
assert not draft.output_shows_exception(""), "empty output shows no exception"

print("OK test_exception_claim")
