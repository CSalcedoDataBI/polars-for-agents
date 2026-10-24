---
name: polars-reference
description: "Use before writing or reviewing Polars code (Python `import polars as pl`): look up whether an expression, method, namespace function or selector exists in the pinned Polars version, its exact signature, whether it is deprecated or unstable, and the traps that produce wrong results. Triggers: writing a Polars transformation, translating pandas or SQL to Polars, an AttributeError or unexpected keyword in Polars, `.str` / `.dt` / `.list` / `.arr` / `.struct` / `.cat` / `.name` namespaces, `group_by`, `join`, `pivot`, `LazyFrame.collect`. Not for pandas, Spark or running pipelines."
---

# Polars reference

Every Polars name in this skill comes from `catalog/polars-<version>.json` at the root of this
repository, exported by introspection of the installed `polars` package. Nothing here is typed
from memory.

## How to use it

1. **Check a name before you write it.** Search the catalogue JSON for the name in its group
   (`Expr`, `Expr.str`, `Expr.dt`, `Expr.list`, `Expr.arr`, `Expr.struct`, `Expr.cat`,
   `Expr.name`, `DataFrame`, `LazyFrame`, `Series`, `functions`, `classes`, `selectors`). If it
   is not there, it does not exist in that version: do not use it.
2. **Read the flags.** `deprecated: true` means use the replacement in `deprecated_message` or the
   docstring. `unstable: true` means the behaviour may change without a major release.
   `parameter_markers` lists single parameters that are deprecated or unstable.
3. **Read the traps** in `notes/` for the group you are writing. Each note has an example that
   was run on the pinned version, with its real output.

## What this is not

- Not pandas: the pandas habits that break in Polars are traps in `notes/`, not an API.
- Not a tutorial. For a hand-written guide, see the `polars` skill in
  [K-Dense-AI/claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills/tree/main/skills/polars) (MIT).
