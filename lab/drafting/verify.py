"""Second, independent pass over the drafts: does each note's prose match what really happened?

draft.py proves that every name exists and every example runs. It cannot prove that the trap's
prose is true. This pass sends each chunk's passing notes, with the output their example really
printed and the docstrings of the APIs they cite, to a fresh call that judges every note:
keep, fix (with a corrected trap text) or drop. Fixed text is name-checked again.

Results are written back into lab/drafting/out/<chunk>.json under "verification"; dropped notes
move to "failed". Spend goes to the same ledger and cap as draft.py.

Usage:  python lab/drafting/verify.py [--budget 35] [--workers 4]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import draft  # noqa: E402
from draft import OUT, Budget, call_claude, catalog_names, ledger_total  # noqa: E402

SCHEMA = HERE / "verify-schema.json"

PROMPT = """You are the independent reviewer for polars-for-agents, a Polars {version} reference
that AI agents trust. Another model drafted the trap notes below. Each example was really run on
polars {version}, and "output" is exactly what it printed. You did not write them.

For each note, decide:
- "keep": every claim in `trap` is supported by the real output or by the docstrings below.
- "fix": the trap is real but its text overstates, misstates or adds an unsupported claim.
  Return the corrected `trap` text (same style: 2 to 5 sentences, Markdown, API names in
  backticks with the qualified form such as `Expr.str.contains`), claiming only what the output
  or docstrings support. Do not change the example.
- "drop": the trap is not real, the output contradicts it, or it is trivia an agent would never
  get wrong.

Be strict about facts and lenient about style. Use only Polars names that appear in the notes or
docstrings below. `reason` is one sentence. For "keep" and "drop", `trap` is an empty string.

Notes (index, then the note with its real output):
{notes}

Docstrings of the APIs the notes cite (truncated):
{docs}
"""


def lookup(catalog: dict) -> dict[str, dict]:
    table = {}
    for group, entries in catalog["groups"].items():
        for e in entries:
            table[draft.qualified(group, e["name"]) if group != "classes" else f"pl.{e['name']}"] = (group, e)
    return table


def verify_chunk(path: Path, catalog: dict, table: dict, budget: Budget, model: str | None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "verification" in data or not data["passed"]:
        return
    notes = "\n\n".join(f"[{i}] {json.dumps(n, indent=1, ensure_ascii=False)}" for i, n in enumerate(data["passed"]))
    cited = sorted({name for n in data["passed"] for name in n["applies_to"] if name in table})
    docs = "\n".join(draft.entry_block(*table[name]) for name in cited)
    prompt = PROMPT.format(version=catalog["polars_version"], notes=notes, docs=docs)
    result = call_claude(prompt, data["chunk"], "verify", budget, model, SCHEMA)
    if result is None:
        return
    verdicts = {v["index"]: v for v in result.get("verdicts", [])}
    kept, failed = [], data["failed"]
    for i, note in enumerate(data["passed"]):
        v = verdicts.get(i, {"verdict": "keep", "reason": "no verdict returned", "trap": ""})
        if v["verdict"] == "drop":
            failed.append({"note": note, "problems": [f"verify: dropped - {v['reason']}"]})
            continue
        if v["verdict"] == "fix" and v.get("trap", "").strip():
            problems = catalog_names.check_markdown(v["trap"])
            if problems:
                failed.append({"note": note, "problems": [f"verify: fixed text failed the name check: {p}" for p in problems]})
                continue
            note = {**note, "trap": v["trap"].strip()}
        kept.append(note)
    data["passed"], data["failed"] = kept, failed
    data["verification"] = [verdicts[i] for i in sorted(verdicts)]
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    counts = {k: sum(1 for v in verdicts.values() if v["verdict"] == k) for k in ("keep", "fix", "drop")}
    print(f"[verified] {data['chunk']}: {counts}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=35.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    if datetime.now(timezone.utc) > datetime(2026, 10, 26, 23, 59, tzinfo=timezone.utc):
        print("promotional credit expired on 2026-10-26: not calling")
        return 1
    catalog = json.loads(catalog_names.catalog_path().read_text(encoding="utf-8"))
    table = lookup(catalog)
    budget = Budget(args.budget)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for path in sorted(OUT.glob("*.json")):
            pool.submit(verify_chunk, path, catalog, table, budget, args.model).add_done_callback(
                lambda f: f.exception() and print(f"[error] {f.exception()!r}"))
    print(f"spent US${ledger_total():.2f} of US${args.budget}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
