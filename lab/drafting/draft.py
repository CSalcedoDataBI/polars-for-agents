"""Draft trap notes and examples per group of the Polars catalogue with `claude-review`.

Lab tooling, not shipped: it spends API credit, so it runs by hand. For each chunk of a catalogue
group it asks Claude for trap notes with a runnable example, using ONLY catalogue names, then:

1. checks every name with scripts/catalog_names.py,
2. runs every example with the installed polars and keeps its stdout,
3. sends the failures back once for a repair.

Drafts land in lab/drafting/out/<chunk>.json; `promote.py` turns the passing ones into
skills/polars-reference/notes/. Spend is capped: every call's cost is read from claude-review's
stderr and appended to out/ledger.jsonl, and no call starts once the cap would be crossed.

Usage:  python lab/drafting/draft.py [--budget 35] [--workers 4] [--only Expr.str]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "scripts"))
import catalog_names  # noqa: E402

CHUNK = 35
DOC_CHARS = 1800
EST_CALL = 0.6  # US$ held back per call in flight, so parallel calls cannot overshoot the cap
SCHEMA = HERE / "schema.json"
COST = re.compile(r"US\$([0-9.]+)\. Acumulado")
LOCK = threading.Lock()


def ledger_total() -> float:
    path = OUT / "ledger.jsonl"
    if not path.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


class Budget:
    def __init__(self, cap: float):
        self.cap, self.in_flight = cap, 0

    def acquire(self) -> bool:
        with LOCK:
            if ledger_total() + (self.in_flight + 1) * EST_CALL > self.cap:
                return False
            self.in_flight += 1
            return True

    def release(self, chunk: str, kind: str, usd: float) -> None:
        with LOCK:
            self.in_flight -= 1
            with (OUT / "ledger.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "chunk": chunk, "kind": kind, "usd": usd}) + "\n")


def chunks(catalog: dict) -> list[tuple[str, list[dict]]]:
    out = []
    for group, entries in catalog["groups"].items():
        if group == "classes":
            continue
        for i in range(0, len(entries), CHUNK):
            part = entries[i : i + CHUNK]
            suffix = f"-{i // CHUNK + 1}" if len(entries) > CHUNK else ""
            out.append((f"{group}{suffix}", part))
    return out


def qualified(group: str, name: str) -> str:
    if group == "functions":
        return f"pl.{name}"
    if group == "selectors":
        return f"cs.{name}"
    return f"{group}.{name}"


def universe(catalog: dict) -> str:
    lines = []
    for group, entries in catalog["groups"].items():
        prefix = {"functions": "pl.", "classes": "pl.", "selectors": "cs."}.get(group, f"{group}.")
        lines.append(f"{group}: " + ", ".join(prefix + e["name"] for e in entries))
    return "\n".join(lines)


def entry_block(group: str, e: dict) -> str:
    flags = [f for f in ("deprecated", "unstable") if e.get(f)]
    head = f"### {qualified(group, e['name'])}  [{e['kind']}{', ' + ', '.join(flags) if flags else ''}]"
    extra = ""
    if e.get("deprecated_message"):
        extra += f"\nDeprecation message: {e['deprecated_message']}"
    if e.get("parameter_markers"):
        extra += f"\nParameter markers: {json.dumps(e['parameter_markers'])}"
    doc = e["doc"][:DOC_CHARS] + (" [...]" if len(e["doc"]) > DOC_CHARS else "")
    return f"{head}\nSignature: {e['signature']}{extra}\n\n{doc}\n"


PROMPT = """You are writing trap notes for polars-for-agents, a Polars reference that AI agents read
before writing Polars code. Its one promise: no agent ever reads an API name that does not exist
in the installed engine. The catalogue below was exported from polars {version} by introspection.

Write 5 to 8 notes for the group "{chunk}". A note is a TRAP: something an agent (or a pandas
user) gets wrong with these APIs. Good traps: pandas or SQL habits that fail or silently differ
(method names, null/NaN semantics, index assumptions, in-place mutation), dtype and null
propagation surprises, defaults that bite (closed intervals, `strict`, `maintain_order`,
`nulls_last`), eager vs lazy differences, deprecated names and their replacement, unstable APIs,
parameters that were deprecated. Prefer the traps that would produce WRONG RESULTS or errors in
real code over trivia. Do not write a note for an API without a real trap.

Rules for every note:
- `title`: one line, imperative or descriptive, no trailing period.
- `applies_to`: the qualified names it is about, exactly as written in the catalogue headers
  below (for example `Expr.str.contains`, `DataFrame.group_by`, `pl.when`, `cs.numeric`).
- `trap`: 2 to 5 sentences of Markdown. Say what goes wrong and what to do instead. Wrap API
  names in backticks using the qualified form. Do not invent behaviour: if the docstring does not
  support a claim, leave it out.
- `example`: a complete Python script, at most 25 lines, that demonstrates the trap and the
  right way. It starts with `import polars as pl` (add `import polars.selectors as cs` only if it
  uses selectors), builds tiny inline data, and ends by printing the results that prove the point.
  It must be deterministic: no randomness, no current date/time, no files, no network, no
  `pl.Config` changes. If showing a failing call, wrap it in try/except and print the exception
  type name only. It must run unmodified on polars {version}.
- Use ONLY Polars names that appear in the full name list below. Never use pandas.

Full list of valid Polars names in {version} (use nothing else):
{universe}

Catalogue entries for this group (signatures and docstrings, truncated):
{entries}
"""

REPAIR = """Some of the notes you drafted for polars-for-agents (group "{chunk}", polars {version})
failed validation. Fix each one so its example runs on polars {version} and uses only valid
names, or drop the note if its trap was wrong. Return the full corrected set of notes for these
failures only, with the same schema. Keep the rules of the original task:

{rules}

Failures (the note as drafted, then what went wrong):
{failures}
"""


def call_claude(prompt: str, chunk: str, kind: str, budget: Budget, model: str | None, schema: Path = SCHEMA) -> dict | None:
    if not budget.acquire():
        print(f"[budget] skip {kind} {chunk}: cap US${budget.cap} reached ({ledger_total():.2f} spent)")
        return None
    usd = 0.0
    try:
        with tempfile.TemporaryDirectory() as tmp:
            p, o = Path(tmp) / "p.md", Path(tmp) / "out.json"
            p.write_text(prompt, encoding="utf-8")
            # The maintainer's claude-review CLI, on PATH; it reads its own API key.
            cmd = [shutil.which("claude-review") or "claude-review",
                   "--prompt-file", str(p), "--schema", str(schema), "-o", str(o)]
            if model:
                cmd += ["--model", model]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
            m = COST.search(r.stderr)
            usd = float(m.group(1)) if m else (EST_CALL if r.returncode == 0 else 0.0)
            print(f"[{kind}] {chunk}: rc={r.returncode} US${usd:.4f} {r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else ''}")
            if r.returncode != 0 or not o.exists():
                return None
            return json.loads(o.read_text(encoding="utf-8"))
    finally:
        budget.release(chunk, kind, usd)


def run_example(code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "example.py"
        f.write_text(code, encoding="utf-8")
        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60, cwd=tmp, env=env)
        except subprocess.TimeoutExpired:
            return False, "timed out after 60 s"
    if r.returncode != 0:
        return False, (r.stderr.strip().splitlines() or ["no stderr"])[-1][:600]
    return True, r.stdout.rstrip()[:3000]


# The idiom the prompt asks for when a note shows a failing call: catch it and print its type
# name. A note that does this is CLAIMING the call raises, so the run must actually raise -- else
# the example proves the opposite of its trap and would teach wrong behaviour.
EXPECTS_EXCEPTION = re.compile(r"type\(\s*\w+\s*\)\.__name__|\.__class__\.__name__|print\(\s*repr\(\s*\w+\s*\)\s*\)")
EXC_IN_OUTPUT = re.compile(r"\b[A-Za-z_]\w*(?:Error|Exception|Warning)\b")


def example_expects_exception(code: str) -> bool:
    return "except" in code and bool(EXPECTS_EXCEPTION.search(code))


def output_shows_exception(output: str) -> bool:
    return bool(EXC_IN_OUTPUT.search(output or ""))


def validate(note: dict) -> list[str]:
    problems = []
    for name in note.get("applies_to", []):
        if not catalog_names.QUALIFIED.match(name):
            problems.append(f"applies_to `{name}` is not a qualified name")
        elif err := catalog_names.check_qualified(name):
            problems.append(err)
    problems += catalog_names.check_markdown(note.get("trap", ""))
    problems += catalog_names.check_code(note.get("example", ""))
    if "import pandas" in note.get("example", ""):
        problems.append("example imports pandas")
    if not problems:
        ok, output = run_example(note["example"])
        if ok:
            note["output"] = output
            # A note that catches and prints an exception type is claiming the call raises. If the
            # run shows no exception, the example contradicts the trap: drop it (reviewer finding).
            if example_expects_exception(note["example"]) and not output_shows_exception(output):
                problems.append("example catches and prints an exception type, but the run shows "
                                "none: the trap's error claim is not demonstrated")
        else:
            problems.append(f"example failed: {output}")
    return problems


def process(chunk: str, entries: list[dict], group: str, catalog: dict, budget: Budget, model: str | None) -> None:
    target = OUT / f"{chunk}.json"
    if target.exists():
        print(f"[skip] {chunk}: already drafted")
        return
    prompt = PROMPT.format(version=catalog["polars_version"], chunk=chunk, universe=universe(catalog),
                           entries="\n".join(entry_block(group, e) for e in entries))
    result = call_claude(prompt, chunk, "draft", budget, model)
    if result is None:
        return
    passed, failed = [], []
    for note in result.get("notes", []):
        problems = validate(note)
        (failed if problems else passed).append((note, problems))
    if failed:
        rules = PROMPT.split("Full list of valid")[0].split("Rules for every note:")[1]
        failures = "\n\n".join(
            f"NOTE:\n{json.dumps(n, indent=1)}\nPROBLEMS:\n- " + "\n- ".join(p) for n, p in failed
        )
        repair = REPAIR.format(chunk=chunk, version=catalog["polars_version"], rules=rules, failures=failures)
        repair += "\nFull list of valid Polars names:\n" + universe(catalog)
        fixed = call_claude(repair, chunk, "repair", budget, model)
        still = []
        for note in (fixed or {}).get("notes", []):
            problems = validate(note)
            (still if problems else passed).append((note, problems) if problems else (note, []))
        failed = still if fixed else failed
    target.write_text(json.dumps({
        "chunk": chunk, "group": group, "polars_version": catalog["polars_version"],
        "passed": [n for n, _ in passed],
        "failed": [{"note": n, "problems": p} for n, p in failed],
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"[done] {chunk}: {len(passed)} passed, {len(failed)} failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=35.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default=None, help="draft only chunks whose name starts with this")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    if datetime.now(timezone.utc) > datetime(2026, 10, 26, 23, 59, tzinfo=timezone.utc):
        print("promotional credit expired on 2026-10-26: not calling")
        return 1
    OUT.mkdir(exist_ok=True)
    catalog = json.loads(catalog_names.catalog_path().read_text(encoding="utf-8"))
    budget = Budget(args.budget)
    work = [(c, e) for c, e in chunks(catalog) if not args.only or c.startswith(args.only)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for chunk, entries in work:
            group = re.sub(r"-\d+$", "", chunk)
            pool.submit(process, chunk, entries, group, catalog, budget, args.model).add_done_callback(
                lambda f: f.exception() and print(f"[error] {f.exception()!r}"))
    print(f"spent US${ledger_total():.2f} of US${args.budget}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
