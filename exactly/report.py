"""Aggregate everything into the four numbers this project exists to produce.

  THE LEADERBOARD, by family rather than as one figure, because counting words, counting
  sentences and counting characters are three different problems and an upper bound is a fourth.

  THE RULE SENSITIVITY, which is the most interesting number here and the one a compliance
  benchmark usually omits. The same responses are re-scored under every alternative counting
  dialect in `rules.py`, one dimension at a time, and the spread between the best and worst
  reading is reported in percentage points. If swapping a defensible word definition moves a
  model ten points, the leaderboard is partly a measurement of the splitter, and the only honest
  response is to publish that number next to it.

  THE ERROR DISTRIBUTION, because off by one and off by forty are not the same failure. Every
  row carries a signed error and the report keeps the histogram, the direction, and the share of
  misses that are off by exactly one.

  THE BASELINES, because a benchmark with no baseline is a file. `filler_keyword` emits the
  requested number of the word `item` with the keyword dropped in and satisfies every check the
  grader makes while saying nothing at all. Its score is the ceiling on what compliance means
  here, and it belongs on the same board as the models.
"""

from __future__ import annotations

import json
import pathlib
import statistics

from . import baselines, generate, grade, recorded, rules

RESULTS = pathlib.Path(__file__).resolve().parent.parent / "results"

# The dimension each dialect group is measured on, and the per row flag that group governs.
SENSITIVITY_FLAG = {"items": "unique_ok"}


def affected(items: list, dimension: str) -> list:
    """The items whose grade can move when `dimension`'s counting rule changes."""
    if dimension == "items":
        return [item for item in items if item["unique"]]
    return [item for item in items if item["dimension"] == dimension]


def system_responses(items: list, fixtures_dir=None) -> list:
    """Every system on the board: the baselines first, then each recorded model.

    Order is fixed rather than sorted by score, so a diff of two report files reads as a change
    in the numbers rather than a reshuffle.
    """
    made = [("reference", "baseline", baselines.responses("reference", items), {})]
    for name in baselines.NAMES:
        made.append((name, "baseline", baselines.responses(name, items), {}))
    for name in recorded.available(fixtures_dir):
        answers, notes = recorded.responses(name, items, fixtures_dir)
        made.append((name, "model", answers, notes))
    return made


def rate(rows: list, flag: str = "count_ok") -> float:
    return round(sum(1 for row in rows if row[flag]) / len(rows), 4) if rows else 0.0


def sensitivity_for(items: list, answers: dict) -> dict:
    """How far one system's compliance moves when a counting rule is swapped for another.

    Measured on the AFFECTED SUBSET, not on all 500. Swapping the word rule cannot change how a
    bullet item is graded, so scoring the change across the whole dataset would divide a real
    effect by five and report a reassuring number that means nothing.
    """
    out = {}
    worst = {"dimension": None, "spread_points": 0.0, "from": None, "to": None}
    for dimension, dialects in sorted(rules.DIALECTS.items()):
        subset = affected(items, dimension)
        if not subset:
            continue
        flag = SENSITIVITY_FLAG.get(dimension, "count_ok")
        published = rules.PUBLISHED[dimension]
        per_dialect = {}
        for dialect in dialects:
            ruleset = rules.ruleset_from({dimension: dialect})
            rows = [grade.grade(item, answers.get(item["id"]), ruleset) for item in subset]
            per_dialect[dialect] = rate(rows, flag)
        values = sorted(per_dialect.items(), key=lambda pair: pair[1])
        spread = round((values[-1][1] - values[0][1]) * 100, 2)
        out[dimension] = {
            "n": len(subset),
            "flag": flag,
            "published": published,
            "published_rate": per_dialect[published],
            "by_dialect": per_dialect,
            "spread_points": spread,
            "lowest": values[0][0],
            "highest": values[-1][0],
        }
        if spread > worst["spread_points"]:
            worst = {"dimension": dimension, "spread_points": spread,
                     "from": values[0][0], "to": values[-1][0]}
    spreads = sorted(entry["spread_points"] for key, entry in out.items() if key != "worst")
    # The median as well as the maximum, because one dialect can dominate and hide the rest. The
    # `no_whitespace` reading of "characters" is the case in point: it moves every character
    # count by the number of spaces in the answer, so it takes the reference from 100 to 0 and
    # would be the only number anybody read if the maximum were quoted alone.
    worst["median_spread_points"] = round(statistics.median(spreads), 2) if spreads else 0.0
    out["worst"] = worst
    return out


def evaluate(items: list, name: str, kind: str, answers: dict, notes: dict) -> dict:
    strict = grade.score(items, answers)
    lenient = grade.score(items, answers, lenient=True)
    unwrapped = sum(1 for row in lenient["rows"] if row["unwrapped"])
    return {
        "system": name,
        "kind": kind,
        "fixture": notes,
        "strict": {"overall": strict["overall"], "families": strict["families"]},
        "lenient_rate": lenient["overall"]["rate"],
        "packaging_gap_points": round(
            (lenient["overall"]["rate"] - strict["overall"]["rate"]) * 100, 2),
        "responses_unwrapped": unwrapped,
        "sensitivity": sensitivity_for(items, answers),
    }


def build(fixtures_dir=None, results_dir=None) -> dict:
    items, meta = generate.load()
    results_dir = RESULTS if results_dir is None else pathlib.Path(results_dir)
    boards = [evaluate(items, name, kind, answers, notes)
              for name, kind, answers, notes in system_responses(items, fixtures_dir)]
    report = {
        "dataset": {
            "count": meta["count"],
            "seed": meta["seed"],
            "prompts_sha256": meta["prompts_sha256"],
            "families": {name: row["n"] for name, row in sorted(meta["families"].items())},
            "published_rules": meta["published_rules"],
        },
        "systems": boards,
        "headline": headline(boards),
    }
    results_dir.mkdir(exist_ok=True)
    (results_dir / "leaderboard.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def headline(boards: list) -> dict:
    """The handful of figures the README and the page quote, computed once and in one place."""
    models = [board for board in boards if board["kind"] == "model"]
    by_name = {board["system"]: board for board in boards}
    spreads = [(board["system"], board["sensitivity"]["worst"]) for board in boards
               if board["sensitivity"]["worst"]["dimension"]]
    biggest = max(spreads, key=lambda pair: pair[1]["spread_points"], default=None)
    return {
        "systems": len(boards),
        "models": len(models),
        "best_model": max((board["system"] for board in models),
                          key=lambda name: by_name[name]["strict"]["overall"]["rate"],
                          default=None),
        "best_model_rate": max((board["strict"]["overall"]["rate"] for board in models),
                               default=None),
        "filler_keyword_rate": by_name["filler_keyword"]["strict"]["overall"]["rate"],
        "ignore_rate": by_name["ignore"]["strict"]["overall"]["rate"],
        "reference_rate": by_name["reference"]["strict"]["overall"]["rate"],
        "largest_sensitivity": {
            "system": biggest[0], "dimension": biggest[1]["dimension"],
            "spread_points": biggest[1]["spread_points"],
            "from": biggest[1]["from"], "to": biggest[1]["to"],
        } if biggest else None,
        "median_sensitivity_across_dimensions": {
            board["system"]: board["sensitivity"]["worst"]["median_spread_points"]
            for board in boards},
    }


def load(results_dir=None) -> dict:
    results_dir = RESULTS if results_dir is None else pathlib.Path(results_dir)
    path = results_dir / "leaderboard.json"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is missing; run `python3 -m exactly report`")
    return json.loads(path.read_text(encoding="utf-8"))


def as_text(report: dict) -> str:
    """The leaderboard as plain text, for a terminal and for the README."""
    lines = []
    dataset = report["dataset"]
    lines.append(f"dataset: {dataset['count']} prompts, seed {dataset['seed']}, "
                 f"sha256 {dataset['prompts_sha256'][:16]}")
    lines.append("")
    # The error columns are over the EXACT families only, because a bound family's signed error
    # is slack rather than aim and pooling the two makes a model that undershoots look high.
    lines.append(f"{'system':<18} {'kind':<9} {'compliant':>9} {'count':>7} {'keyword':>8} "
                 f"{'off-by-1':>9} {'exact err':>9} {'worst rule swing':>17}")
    ordered = sorted(report["systems"],
                     key=lambda board: -board["strict"]["overall"]["rate"])
    for board in ordered:
        overall = board["strict"]["overall"]
        errors = overall["errors_exact"]
        worst = board["sensitivity"]["worst"]
        swing = (f"{worst['spread_points']:.1f}pt {worst['dimension']}"
                 if worst["dimension"] else "none")
        share = errors["off_by_one_share_of_misses"]
        lines.append(
            f"{board['system']:<18} {board['kind']:<9} "
            f"{overall['rate'] * 100:>8.1f}% {overall['count_ok']:>7} {overall['keyword_ok']:>8} "
            f"{('-' if share is None else format(share * 100, '.0f') + '%'):>9} "
            f"{errors['mean_error']:>9.2f} {swing:>17}")
    return "\n".join(lines)
