"""Promote the passing drafts in lab/drafting/out/ to skills/polars-reference/notes/.

One Markdown file per catalogue group. A note is promoted only if it passed in draft.py (names
checked against the catalogue, example run on the pinned polars) and passes the name check
again here. The example's real output, as captured when it ran, goes under it.

Usage:  python lab/drafting/promote.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import catalog_names  # noqa: E402

NOTES = ROOT / "skills" / "polars-reference" / "notes"


def slug(group: str) -> str:
    return group.lower().replace(".", "-")


def render(group: str, version: str, notes: list[dict]) -> str:
    out = [
        f"# {group}: traps",
        "",
        f"Drafted with Claude and checked by machine against polars {version}: every name below is in",
        f"`catalog/polars-{version}.json`, and every example was run on that version. The output",
        "under each example is what it printed.",
        "",
    ]
    for note in notes:
        out += [
            f"## {note['title']}",
            "",
            "Applies to: " + ", ".join(f"`{n}`" for n in note["applies_to"]),
            "",
            note["trap"].strip(),
            "",
            "```python",
            note["example"].rstrip(),
            "```",
            "",
            "Output:",
            "",
            "```text",
            note.get("output", "").rstrip() or "(no output)",
            "```",
            "",
        ]
    return "\n".join(out)


def main() -> int:
    by_group: dict[str, list[dict]] = defaultdict(list)
    version = None
    for draft in sorted((HERE / "out").glob("*.json")):
        data = json.loads(draft.read_text(encoding="utf-8"))
        version = data["polars_version"]
        by_group[data["group"]].extend(data["passed"])
    NOTES.mkdir(parents=True, exist_ok=True)
    total = rejected = 0
    for group, notes in sorted(by_group.items()):
        text = render(group, version, notes)
        problems = catalog_names.check_markdown(text)
        if problems:
            # Drop the offending notes one by one rather than the whole group.
            kept = [n for n in notes if not catalog_names.check_markdown(render(group, version, [n]))]
            rejected += len(notes) - len(kept)
            notes, text = kept, render(group, version, kept)
        if not notes:
            continue
        (NOTES / f"{slug(group)}.md").write_text(text, encoding="utf-8", newline="\n")
        total += len(notes)
    print(f"promoted {total} notes in {len(by_group)} groups ({rejected} rejected by the name check)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
