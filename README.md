# polars-for-agents

> **Pre-release.** This repository is public from day one, but nothing in it is ready to install
> yet. The API catalogue has not been generated, and there is no plugin to add. Watch the
> repository or follow the [v0.1 epic](https://github.com/CSalcedoDataBI/polars-for-agents/issues/2)
> if you want to know when that changes.

The Polars reference for AI agents: every expression, method, namespace and selector
**exported from the installed `polars` package itself** instead of typed from memory. Each entry
comes with its signature, its docstring, the Polars version it was exported from, and whether it
is deprecated or unstable, plus the gotchas the documentation leaves out.

It is the sibling of [dax-for-agents](https://github.com/CSalcedoDataBI/dax-for-agents),
[powerquery-m-for-agents](https://github.com/CSalcedoDataBI/powerquery-m-for-agents) and
[spark-for-agents](https://github.com/CSalcedoDataBI/spark-for-agents), and it follows the same
rule: **an agent never reads a name that did not come from the engine.**

## What it will contain

| Piece | Source | Status |
|---|---|---|
| API catalogue (`pl.Expr` and its `.str`, `.dt`, `.list`, `.arr`, `.struct`, `.cat`, `.name` namespaces; `DataFrame`, `LazyFrame`, `Series`; top-level functions and classes; selectors) | `scripts/export_catalog.py`, introspection of the installed `polars` package, pinned by version in [`catalog/`](catalog/) | first export in review |
| Deprecated and unstable flags, for the whole API and per parameter | the same introspection | first export in review |
| Traps and examples | [`skills/polars-reference/notes/`](skills/polars-reference/notes/): drafted with Claude, every name checked against the catalogue, every example run on the pinned version with its real output | first drafts in review |
| Name check | `scripts/catalog_names.py`, run by the required `Validate` check on every Markdown file under `skills/` | in review |
| `polars-feedback` skill | report a wrong or missing entry as a public issue | planned |

## Not in scope

- Running pipelines. This is a reference an agent reads, not an executor.
- pandas. That is `pandas-for-agents`.
- A tutorial. For a hand-written Polars guide, see the `polars` skill in
  [K-Dense-AI/claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills/tree/main/skills/polars) (MIT).

## License

[MIT](LICENSE).
