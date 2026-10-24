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

## Does the reference stop invented names?

That is the whole reason this repository exists, so it is measured, not asserted. Each question
in the [bank](evals/hallucination/questions.yaml) is asked twice of the same model: once alone
(arm A), and once with the catalogue rows of its category (arm B — names and one-line summaries,
never the card that holds the answer). Every Polars name an answer writes **in runnable code** is
looked up with the repo's own checker ([`scripts/catalog_names.py`](scripts/catalog_names.py)); a
name the export does not have is an invention. No model judges another, and any saved run recounts
for free with `--replay`.

| Model | Questions compared | Invented, without the reference | Invented, with it |
|---|---|---|---|
| Claude Haiku 5.5 | 23 | 0 | 0 |
| Claude Haiku 4.5 | 23 | 1 | 2 |

The honest reading: a current Claude model does not invent Polars names on this bank, with the
reference or without it — Polars is popular and well-represented, and the model has seen it
thousands of times. The reference earns its keep elsewhere: on weaker models, and on the genuinely
obscure corners (the `Expr.arr` array namespace is where Haiku 4.5 slipped, and the catalogue's
rows did not save it — a reminder that a list of names is a weaker aid than an open card). The
value here is the **measurement that keeps working**: it will catch a regression, and it will show
the gap the day a cheaper or older model is put behind an agent.

```bash
python evals/hallucination/run_ab.py --model claude-haiku-5-5 --out run.json
python evals/hallucination/run_ab.py --replay evals/hallucination/runs/2026-10-23-claude-haiku-4-5.json
python evals/hallucination/test_run_ab.py
```

Raw answers for every run are in [`evals/hallucination/runs/`](evals/hallucination/runs/). The eval
calls the Anthropic or DeepSeek API with `ANTHROPIC_API_KEY` or `DEEPSEEK_API_KEY` read from the
environment (never from the command line, never written into the run file); `--replay` sends
nothing.

## Not in scope

- Running pipelines. This is a reference an agent reads, not an executor.
- pandas. That is `pandas-for-agents`.
- A tutorial. For a hand-written Polars guide, see the `polars` skill in
  [K-Dense-AI/claude-scientific-skills](https://github.com/K-Dense-AI/claude-scientific-skills/tree/main/skills/polars) (MIT).

## License

[MIT](LICENSE).
