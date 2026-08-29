"""Read the answers a real model already gave, from files that are committed to git.

Every fixture row carries the SHA-256 of the prompt it was answered from. That field is the whole
reason this module exists as something other than a two line `json.loads`. Prompts are generated
from a seed, and a seed is easy to change by accident: edit a template, reorder a family, add a
topic, and every prompt shifts while the recorded answers stay where they are. The result would be
a leaderboard scoring last week's answers against this week's questions, and it would look
completely normal.

So the check is not optional and it is not a warning. A fixture whose prompt digest does not match
the prompt with the same id is a hard failure, named and counted, and `verify.sh` fails on it.

The second guard here is about truncation. A response that stopped because it exhausted the
generation budget is a sentence cut in half rather than an attempt at the constraint, and grading
it as a counting failure turns the leaderboard into a measurement of `num_predict`. Measured on
this workstation, gpt-oss:20b accepts `think: false` and then spends all 1200 tokens of the
budget on a hidden reasoning channel ollama strips out, returning nineteen visible characters.
Every fixture row therefore records why generation stopped, the truncated share is reported next
to the score, and a fixture over `TRUNCATION_LIMIT` is refused rather than quietly scored.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

DIR = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "responses"


# Above this share of responses cut off by the generation budget, the fixture is measuring the
# budget rather than the model and is refused. Some truncation is tolerable and worth reporting;
# a fixture that is mostly truncation is not a record of anything.
TRUNCATION_LIMIT = 0.10


class StaleFixture(RuntimeError):
    """A recorded answer belongs to a prompt that no longer exists in this form."""


class TruncatedFixture(RuntimeError):
    """Too many recorded answers ran out of generation budget to be worth scoring."""


class PartialFixture(RuntimeError):
    """A fixture that does not cover the whole dataset.

    Refused rather than scored on what it happens to contain. The families are not the same
    difficulty, and a partial file is a prefix of the dataset order, so scoring one would report
    the score of whichever families the run reached before it stopped. A model that cannot be
    recorded in full belongs off the board, not on it with a footnote.
    """


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
    """(responses by item id, notes), or one of three refusals.

    `StaleFixture` when a recorded answer's prompt digest no longer matches the prompt with that
    id, `PartialFixture` when the file does not cover the whole dataset, and `TruncatedFixture`
    when too many answers stopped at the generation budget. All three are refusals rather than
    warnings, because each one produces a number that looks completely ordinary on a leaderboard
    and means something other than what the column header says.
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
    if missing:
        raise PartialFixture(
            f"{name}: {len(missing)} of {len(wanted)} items have no recorded answer, starting at "
            f"{missing[0]}. Finish the recording or remove the fixture; a partial file scores "
            f"whichever families the run reached, not the model.")
    truncated = sorted(item_id for item_id, row in rows.items() if row.get("truncated"))
    share = round(len(truncated) / len(rows), 4) if rows else 0.0
    if share > TRUNCATION_LIMIT:
        raise TruncatedFixture(
            f"{name}: {len(truncated)} of {len(rows)} responses ({share * 100:.1f}%) stopped at "
            f"the generation budget, above the {TRUNCATION_LIMIT * 100:.0f}% limit. Re-record "
            f"with a larger --num-predict; scoring this would measure the budget, not the model.")
    reasoning = [row.get("thinking_chars", 0) for row in rows.values()]
    budgets = sorted({row.get("num_predict", 0) for row in rows.values()})
    notes = {
        "rows": len(rows),
        "missing": len(missing),
        "transport_errors": len(errors),
        "truncated": len(truncated),
        "truncated_share": share,
        "max_thinking_chars": max(reasoning) if reasoning else 0,
        # A repaired fixture holds rows recorded at more than one budget. Publishing the range
        # rather than one number keeps that visible instead of implying a single clean run.
        "num_predict": budgets,
        "first_missing": missing[0] if missing else None,
    }
    return answered, notes
