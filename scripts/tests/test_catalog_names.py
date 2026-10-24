"""Regression tests for `catalog_names.check_code`'s known false positives.

Every case here is a legitimate Python or Polars idiom a drafted example uses that the name check
must NOT count as an invented name, plus one genuinely invented name it still must catch. Standard
library only, no pytest: run `python scripts/tests/test_catalog_names.py` (the Validate workflow
runs it too).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import catalog_names as cn  # noqa: E402


def no_errors(code: str, label: str) -> None:
    errors = cn.check_code(code)
    assert not errors, f"{label}: expected no errors, got {errors}"


def has_error(code: str, label: str) -> None:
    errors = cn.check_code(code)
    assert errors, f"{label}: expected an error, got none"


# `type(e).__name__`: printing the class name of a caught exception is Python, not a Polars name.
no_errors(
    "import polars as pl\n"
    "try:\n"
    "    pl.Series([1, 2]).item()\n"
    "except Exception as e:\n"
    "    print(type(e).__name__)\n",
    "dunder __name__",
)

# The `pl.when(...).then(...).otherwise(...)` chain: then/otherwise are real engine methods.
no_errors(
    'import polars as pl\n'
    'df = pl.DataFrame({"x": [-1, 0, 1]})\n'
    'print(df.select(pl.when(pl.col("x") > 0).then(1).otherwise(0)))\n',
    "when/then/otherwise chain",
)

# File-like buffer methods from io: reading and writing in memory instead of to a file.
no_errors(
    'import polars as pl\n'
    'import io\n'
    'buf = io.BytesIO()\n'
    'pl.DataFrame({"a": [1, 2]}).write_parquet(buf)\n'
    'buf.seek(0)\n'
    'print(len(buf.getvalue()) > 0)\n',
    "io buffer methods",
)

# An invented method on a Polars object must still be flagged -- the protection is not weakened.
has_error(
    'import polars as pl\npl.col("x").totally_made_up_method()\n',
    "invented method still caught",
)

# A dunder skip must not let an invented bare name through elsewhere.
has_error(
    'import polars as pl\npl.not_a_real_function()\n',
    "invented pl.* still caught",
)

print("OK test_catalog_names (5 cases)")
