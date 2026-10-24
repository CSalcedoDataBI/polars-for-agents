"""Check that a text names only Polars APIs that exist in the exported catalogue.

Used by `check_repo.py` (CI) on every Markdown file under `skills/`, and by the drafting lab on
every draft before it can be promoted. Standard library only.

What counts as a Polars name:

- In ```python blocks: `pl.<x>` and `cs.<x>` (module level), every `.attr` accessed on anything
  that is not another imported module (it must be a member of some catalogue group, or a
  namespace such as `str`), and every keyword argument passed to such a call (it must be a
  parameter of some catalogue entry with that name, unless one of them takes **kwargs).
- In prose: inline code spans that look qualified, such as `pl.col`, `cs.numeric`,
  `Expr.str.contains`, `DataFrame.group_by` or `LazyFrame.collect`.
"""

from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ("Expr", "DataFrame", "LazyFrame", "Series")
CODE_BLOCK = re.compile(r"```python\n(.*?)```", re.S)
INLINE = re.compile(r"`([^`\n]+)`")
QUALIFIED = re.compile(r"^(pl|cs|Expr|DataFrame|LazyFrame|Series)((?:\.[A-Za-z_]\w*)+)(?:\(.*\))?$")
# Python builtins that examples use on Polars results (`df.shape`, `.items()` on a dict).
PYTHON_ATTRS = {"items", "keys", "values", "append", "join", "format", "upper", "lower", "split", "strip"}
# A dunder attribute is Python's, never a Polars API name: `type(e).__name__` prints an exception
# class name, the idiom the drafting prompt asks for when showing a failing call.
DUNDER = re.compile(r"^__\w+__$")
# Methods of file-like buffers (`io.StringIO`/`io.BytesIO`) that an example uses to read or write
# in memory instead of touching a file. None of these is a member of any Polars class.
IO_ATTRS = {"read", "write", "seek", "tell", "getvalue", "getbuffer", "readline", "readlines",
            "truncate", "flush", "close"}
# Real Polars methods reached through the `pl.when(...).then(...).otherwise(...)` chain. They live
# on the private `When`/`Then` classes (`polars.expr.whenthen`), which are not in `pl.__all__`, so
# the `__all__`-scoped export does not list them. They exist in the installed engine, so naming
# them is not invention -- the one promise this check protects is kept.
WHENTHEN = {"then", "otherwise"}


def catalog_path() -> Path:
    paths = sorted((ROOT / "catalog").glob("polars-*.json"))
    if len(paths) != 1:
        raise SystemExit(f"expected exactly one catalog/polars-*.json, found {len(paths)}")
    return paths[0]


@lru_cache(maxsize=1)
def load() -> dict:
    data = json.loads(catalog_path().read_text(encoding="utf-8"))
    groups = data["groups"]
    params: dict[str, set[str]] = {}
    var_kw: set[str] = set()
    for entries in groups.values():
        for e in entries:
            sig = e["signature"]
            inner = sig[sig.find("(") + 1 : sig.rfind(")")] if "(" in sig else ""
            names = set(re.findall(r"(?:^|,\s*)\*{0,2}([A-Za-z_]\w*)", inner))
            params.setdefault(e["name"], set()).update(names)
            if re.search(r"\*\*[A-Za-z_]", inner):
                var_kw.add(e["name"])
    members = {e["name"] for g, es in groups.items() if g not in ("functions", "selectors", "classes") for e in es}
    return {
        "version": data["polars_version"],
        "groups": {g: {e["name"] for e in es} for g, es in groups.items()},
        "pl": {e["name"] for e in groups["functions"]} | {e["name"] for e in groups["classes"]} | {"selectors"},
        "cs": {e["name"] for e in groups["selectors"]},
        "members": members,
        "params": params,
        "var_kw": var_kw,
    }


def check_qualified(name: str) -> str | None:
    cat = load()
    m = QUALIFIED.match(name)
    if not m:
        return None
    root, parts = m.group(1), m.group(2).lstrip(".").split(".")
    if root == "pl":
        return None if parts[0] in cat["pl"] else f"`pl.{parts[0]}` is not in polars {cat['version']}"
    if root == "cs":
        return None if parts[0] in cat["cs"] else f"`cs.{parts[0]}` is not in polars.selectors {cat['version']}"
    group, rest = root, parts
    if root == "Expr" and len(parts) > 1 and f"Expr.{parts[0]}" in cat["groups"]:
        group, rest = f"Expr.{parts[0]}", parts[1:]
    if rest[0] not in cat["groups"][group]:
        return f"`{name}`: `{rest[0]}` is not a member of {group} in polars {cat['version']}"
    return None


def check_code(code: str) -> list[str]:
    cat = load()
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"python block does not parse: {exc.msg} (line {exc.lineno})"]
    errors = []
    other_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name.startswith("polars"):
                    other_modules.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                bound = alias.asname or alias.name
                if mod == "polars":
                    if alias.name not in cat["pl"] and alias.name != "selectors":
                        errors.append(f"`from polars import {alias.name}`: not in polars {cat['version']}")
                elif not mod.startswith("polars"):
                    other_modules.add(bound)

    def root_name(node: ast.AST) -> str | None:
        while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
            node = node.func if isinstance(node, ast.Call) else node.value
        return node.id if isinstance(node, ast.Name) else None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in ("pl", "cs"):
                if node.attr not in cat[node.value.id]:
                    errors.append(f"`{node.value.id}.{node.attr}` is not in polars {cat['version']}")
                continue
            if (root_name(node) in other_modules or node.attr in PYTHON_ATTRS
                    or DUNDER.match(node.attr) or node.attr in IO_ATTRS or node.attr in WHENTHEN):
                continue
            if node.attr not in cat["members"] and node.attr not in cat["groups"].get("Expr", set()):
                errors.append(f"`.{node.attr}` is not a member of any Polars class in {cat['version']}")
        elif isinstance(node, ast.Call) and node.keywords:
            func = node.func
            if isinstance(func, ast.Attribute):
                name, root = func.attr, root_name(func)
            elif isinstance(func, ast.Name):
                name, root = func.id, None
            else:
                continue
            if root in other_modules or name not in cat["params"] or name in cat["var_kw"]:
                continue
            for kw in node.keywords:
                if kw.arg and kw.arg not in cat["params"][name]:
                    errors.append(f"`{name}(..., {kw.arg}=...)`: no Polars `{name}` takes `{kw.arg}` in {cat['version']}")
    return sorted(set(errors))


def check_markdown(text: str) -> list[str]:
    errors = []
    for block in CODE_BLOCK.findall(text):
        errors += check_code(block)
    prose = CODE_BLOCK.sub("", text)
    for span in INLINE.findall(prose):
        problem = check_qualified(span.strip())
        if problem:
            errors.append(problem)
    return sorted(set(errors))
