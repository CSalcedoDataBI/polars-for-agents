"""Export the Polars API catalogue from the installed `polars` package.

Every name an agent reads in this repository must come from this file's output,
`catalog/polars-<version>.json`. Nothing in it is typed by hand: the script walks the public
members of the installed package with `inspect` and records, for each one, its kind, its
signature, its docstring, and whether Polars marks it deprecated or unstable.

Groups exported (see docs/superpowers/specs/2026-10-23-polars-for-agents-design.md, section 2):

- `Expr` and its namespaces `Expr.str`, `Expr.dt`, `Expr.list`, `Expr.arr`, `Expr.struct`,
  `Expr.cat`, `Expr.name`
- `DataFrame`, `LazyFrame`, `Series`
- `functions`: callables in `polars.__all__` that are not classes
- `classes`: classes in `polars.__all__` (data types, frames, exceptions, config), name and
  docstring only; their members are exported in the groups above when they matter
- `selectors`: functions in `polars.selectors.__all__`

Usage:  python scripts/export_catalog.py          (writes catalog/polars-<installed version>.json)
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

import polars as pl
import polars.selectors as cs

ROOT = Path(__file__).resolve().parent.parent
UNSTABLE = re.compile(r"considered\s+\*\*unstable\*\*", re.I)
# A directive at column 0 marks the whole object; an indented one sits under a parameter.
DIRECTIVE = re.compile(r"^( *)\.\. (deprecated|warning)::[ \t]*(\S*)", re.M)

EXPR_NAMESPACES = ("str", "dt", "list", "arr", "struct", "cat", "name")


def directives(doc: str) -> tuple[str | None, bool, list[dict]]:
    """Read `.. deprecated::` and unstable `.. warning::` blocks from a numpydoc docstring.

    Returns (object deprecated since, object unstable, parameter-level markers).
    """
    lines = doc.splitlines()
    since, unstable, params = None, False, []
    for match in DIRECTIVE.finditer(doc):
        indent, directive, version = len(match.group(1)), match.group(2), match.group(3)
        row = doc.count("\n", 0, match.start())
        body = []
        for line in lines[row + 1 :]:
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
        if directive == "warning" and not UNSTABLE.search(" ".join(body)):
            continue
        if indent == 0:
            if directive == "deprecated":
                since = version or since
            else:
                unstable = True
            continue
        # The owner is the closest line above with less indentation: the parameter name.
        owner = next(
            (l.strip() for l in reversed(lines[:row]) if l.strip() and len(l) - len(l.lstrip()) < indent),
            None,
        )
        marker = {"parameter": owner.split(" :")[0] if owner else None, "marker": "deprecated" if directive == "deprecated" else "unstable"}
        if directive == "deprecated":
            marker["since"] = version or None
        params.append(marker)
    return since, unstable, params


def describe(name: str, obj: object, kind: str) -> dict:
    doc = inspect.getdoc(obj) or ""
    try:
        signature = f"{name}{inspect.signature(obj)}" if kind != "property" else name
    except (TypeError, ValueError):
        signature = name
    # getattr_static: `pl.col` answers any attribute with an Expr, which has no truth value.
    try:
        deprecated_msg = inspect.getattr_static(obj, "__deprecated__")
    except AttributeError:
        deprecated_msg = None
    since, unstable, params = directives(doc)
    entry = {
        "name": name,
        "kind": kind,
        "signature": signature,
        "summary": doc.split("\n\n", 1)[0].replace("\n", " ").strip(),
        "deprecated": bool(deprecated_msg or since),
        "unstable": unstable,
    }
    if deprecated_msg or since:
        entry["deprecated_since"] = since
        entry["deprecated_message"] = deprecated_msg if isinstance(deprecated_msg, str) else None
    if params:
        entry["parameter_markers"] = params
    entry["doc"] = doc
    return entry


def class_members(cls: type) -> list[dict]:
    entries = []
    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        static = inspect.getattr_static(cls, name)
        if isinstance(static, property):
            entries.append(describe(name, static, "property"))
        elif isinstance(static, (staticmethod, classmethod)) or callable(static):
            entries.append(describe(name, getattr(cls, name), "method"))
    return entries


def namespace_class(name: str) -> type:
    """The class behind `pl.Expr.<name>` (a property returning a namespace object)."""
    return type(getattr(pl.col("x"), name))


def build() -> dict:
    groups: dict[str, list[dict]] = {"Expr": class_members(pl.Expr)}
    for ns in EXPR_NAMESPACES:
        groups[f"Expr.{ns}"] = class_members(namespace_class(ns))
    for cls in (pl.DataFrame, pl.LazyFrame, pl.Series):
        groups[cls.__name__] = class_members(cls)
    groups["functions"] = [
        describe(name, getattr(pl, name), "function")
        for name in sorted(pl.__all__)
        if callable(getattr(pl, name, None)) and not inspect.isclass(getattr(pl, name))
    ]
    groups["classes"] = [
        describe(name, getattr(pl, name), "class") for name in sorted(pl.__all__) if inspect.isclass(getattr(pl, name, None))
    ]
    groups["selectors"] = [
        describe(name, getattr(cs, name), "function")
        for name in sorted(cs.__all__)
        if inspect.isfunction(getattr(cs, name, None))
    ]
    return {
        "polars_version": pl.__version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "generated_by": "scripts/export_catalog.py",
        "counts": {group: len(entries) for group, entries in groups.items()},
        "groups": groups,
    }


def main() -> int:
    catalog = build()
    out = ROOT / "catalog" / f"polars-{catalog['polars_version']}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    total = sum(catalog["counts"].values())
    print(f"wrote {out.relative_to(ROOT).as_posix()}: {total} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
