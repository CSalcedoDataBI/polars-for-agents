"""Repository checks that run in CI (the required `Validate` check).

- Every skills/*/SKILL.md opens with frontmatter that has `name` (matching its folder) and
  `description`.
- Every workflow job sets `timeout-minutes` and runs on `ubuntu-latest`, and every workflow
  declares `concurrency` (Actions cost rules R2, R3, R5).
- The catalogue JSON is the export script's output, and its counts match its entries.
- Every Markdown file under skills/ names only Polars APIs that are in the catalogue
  (`catalog_names.py`).

Standard library only, so CI needs no install step. Exit code 1 lists every failure.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import catalog_names

ROOT = Path(__file__).resolve().parent.parent


def check_skills() -> list[str]:
    errors = []
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        rel = skill.relative_to(ROOT).as_posix()
        if not match:
            errors.append(f"{rel}: missing frontmatter")
            continue
        fields = dict(
            line.split(":", 1) for line in match.group(1).splitlines() if ":" in line and not line.startswith(" ")
        )
        name = fields.get("name", "").strip()
        if name != skill.parent.name:
            errors.append(f"{rel}: name '{name}' does not match folder '{skill.parent.name}'")
        if not fields.get("description", "").strip():
            errors.append(f"{rel}: empty description")
    return errors


def check_workflows() -> list[str]:
    errors = []
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        text = wf.read_text(encoding="utf-8")
        rel = wf.relative_to(ROOT).as_posix()
        if not re.search(r"^concurrency:", text, re.M):
            errors.append(f"{rel}: no top-level concurrency (R2)")
        jobs = len(re.findall(r"^\s+runs-on:", text, re.M))
        timeouts = len(re.findall(r"^\s+timeout-minutes:", text, re.M))
        if timeouts < jobs:
            errors.append(f"{rel}: {jobs} jobs but {timeouts} timeout-minutes (R3)")
        for runner in re.findall(r"^\s+runs-on:\s*(.+)$", text, re.M):
            if runner.strip() != "ubuntu-latest":
                errors.append(f"{rel}: runs-on {runner.strip()} (R5, and no self-hosted on a public repo)")
    return errors


def check_catalog() -> list[str]:
    """The catalogue is the export script's output, untouched, and the checker still bites."""
    data = json.loads(catalog_names.catalog_path().read_text(encoding="utf-8"))
    errors = []
    if data.get("generated_by") != "scripts/export_catalog.py":
        errors.append("catalog: not written by scripts/export_catalog.py")
    for group, entries in data["groups"].items():
        if data["counts"].get(group) != len(entries):
            errors.append(f"catalog: counts[{group}] does not match its {len(entries)} entries (edited by hand?)")
    # A known-bad example must fail, or the name check is not checking anything.
    if not catalog_names.check_code("import polars as pl\npl.col('a').str.contanis('x')\npl.colum('b')"):
        errors.append("catalog_names: an invented name passed the check")
    return errors


def check_names() -> list[str]:
    """Every Markdown file an agent reads names only what the catalogue has (CLAUDE.md rule 1)."""
    errors = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        rel = md.relative_to(ROOT).as_posix()
        errors += [f"{rel}: {problem}" for problem in catalog_names.check_markdown(md.read_text(encoding="utf-8"))]
    return errors


def main() -> int:
    errors = check_skills() + check_workflows() + check_catalog() + check_names()
    for error in errors:
        print(f"FAIL {error}")
    if not errors:
        print("OK repo checks")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
