"""Read the answers a real model already gave, from files that are committed to git.

Every fixture row carries the SHA-256 of the prompt it was answered from. That field is the whole
reason this module exists as something other than a two line `json.loads`. Prompts are generated
from a seed, and a seed is easy to change by accident: edit a template, reorder a family, add a
topic, and every prompt shifts while the recorded answers stay where they are. The result would be
a leaderboard scoring last week's answers against this week's questions, and it would look
completely normal.

So the check is not optional and it is not a warning. A fixture whose prompt digest does not match
the prompt with the same id is a hard failure, named and counted, and `verify.sh` fails on it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

DIR = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "responses"


class StaleFixture(RuntimeError):
    """A recorded answer belongs to a prompt that no longer exists in this form."""


def prompt_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def available(directory=None) -> list:
    """The model names with a committed fixture file, in a stable order."""
    directory = DIR if directory is None else pathlib.Path(directory)
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.jsonl"))


def read(name: str, directory=None) -> dict:
    """The raw rows of one fixture file, keyed by item id."""
    directory = DIR if directory is None else pathlib.Path(directory)
    path = directory / (name + ".jsonl")
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def responses(name: str, items: list, directory=None) -> tuple:
    """(responses by item id, notes). Raises `StaleFixture` if a digest does not match.

    An item with no row at all is left out of the mapping rather than filled with an empty
    string, because `grade.score` already treats a missing id as an empty answer and counts it as
    a failure. Recording that separately keeps "the model was never asked" distinguishable from
    "the model answered with nothing", which are different facts about a run.
    """
    rows = read(name, directory)
    wanted = {item["id"]: item["prompt"] for item in items}
    stale = []
    for item_id, row in sorted(rows.items()):
        if item_id not in wanted:
            stale.append(f"{item_id} is not an item in this dataset")
            continue
        recorded_digest = row.get("prompt_sha256")
        if recorded_digest != prompt_digest(wanted[item_id]):
            stale.append(f"{item_id} was answered from a different prompt")
    if stale:
        raise StaleFixture(f"{name}: {len(stale)} stale row(s); first is {stale[0]}. "
                           f"Re-record with scripts/record.py --model {name.replace('_', ':', 1)}")
    answered = {item_id: row.get("response", "") for item_id, row in rows.items()}
    errors = sorted(item_id for item_id, row in rows.items() if row.get("error"))
    missing = sorted(item_id for item_id in wanted if item_id not in rows)
    notes = {
        "rows": len(rows),
        "missing": len(missing),
        "transport_errors": len(errors),
        "first_missing": missing[0] if missing else None,
    }
    return answered, notes
