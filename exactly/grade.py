"""Grade one response, and aggregate a set of them into the numbers the leaderboard reports.

Three decisions here are worth arguing with, which is why they are written down rather than
buried.

  THE NEAR MISS IS THE SIGNAL. A pass rate throws away the difference between a model that wrote
  8 bullets when asked for 7 and one that wrote 40. Every row carries a SIGNED error, and the
  report keeps the distribution, the direction and the share of failures that are off by exactly
  one. "Produces 8 when asked for 7" and "produces 5 when asked for 7" are different problems and
  a single percentage cannot tell them apart.

  A BOUND IS NOT A TARGET. `no more than 4 sentences` is satisfied by 1, so a system that simply
  writes less scores well on it. The families are kept apart in the leaderboard for exactly that
  reason, and the signed error is still recorded for bound families so the slack is visible.

  LENIENT GRADING IS A SECOND READING, NOT A REPLACEMENT. Models wrap answers in preambles, code
  fences and self-reported counts. Every prompt asks them not to. Rather than quietly stripping
  that and calling it compliance, both readings are reported, and the difference between them is
  a number in its own right: how much of the failure is counting and how much is packaging.
"""

from __future__ import annotations

import re
import statistics

from . import rules

FENCE = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\s*\n(?P<body>.*?)\n\s*```\s*$", re.DOTALL)
PREAMBLE = re.compile(r"^[^\n]{0,120}:[ \t]*\n")
SELF_COUNT = re.compile(r"^\(?\s*(?:that is |this is |exactly )?\d+\s+"
                        r"(?:words?|characters?|chars?|sentences?|bullets?|lines?|paragraphs?|"
                        r"items?)\b[^\n]*$", re.IGNORECASE)


def unwrap(text: str):
    """Strip the packaging every prompt asked the model not to add. Returns (text, notes)."""
    notes = []
    body = text.strip()
    match = FENCE.match(body)
    if match:
        body = match.group("body")
        notes.append("code fence")
    stripped = PREAMBLE.match(body)
    if stripped and rules.count_words(body.split("\n", 1)[0]) <= 14:
        body = body[stripped.end():]
        notes.append("preamble line")
    parts = body.rstrip().split("\n")
    while len(parts) > 1 and SELF_COUNT.match(parts[-1].strip()):
        parts.pop()
        notes.append("self reported count")
    return "\n".join(parts).strip(), notes


def satisfies(mode: str, observed: int, target: int) -> bool:
    if mode == "exact":
        return observed == target
    if mode == "at_most":
        return observed <= target
    if mode == "at_least":
        return observed >= target
    raise ValueError(f"no such mode: {mode!r}")


def keyword_present(text: str, keyword: str) -> bool:
    """Whole-word, case insensitive, and a hyphenated compound counts as containing its parts."""
    wanted = keyword.casefold()
    found = set()
    for token in rules.words(text, "hyphen_split"):
        found.add("".join(ch for ch in token if ch.isalnum()).casefold())
    return wanted in found


def grade(item: dict, response, ruleset=None, lenient: bool = False) -> dict:
    """One response against one item. Never raises on a malformed response."""
    raw = "" if response is None else str(response)
    notes = []
    text = raw.strip()
    if lenient:
        text, notes = unwrap(raw)
    observed = rules.count(item["dimension"], text, ruleset)
    target = item["target"]
    count_ok = satisfies(item["mode"], observed, target)
    keyword_ok = keyword_present(text, item["keyword"])
    repeats = []
    unique_ok = True
    if item["unique"]:
        ruleset = rules.PUBLISHED if ruleset is None else ruleset
        repeats = rules.duplicate_items(text, ruleset.get("bullets", "plain"),
                                        ruleset.get("items", "normalized"))
        unique_ok = not repeats
    reasons = []
    if not text:
        reasons.append("the response is empty")
    if not count_ok:
        reasons.append(f"{observed} {item['dimension']} against a target of {target}")
    if not keyword_ok:
        reasons.append(f"the required word {item['keyword']!r} is missing")
    if not unique_ok:
        reasons.append(f"{len(repeats)} repeated item(s)")
    return {
        "id": item["id"], "family": item["family"], "dimension": item["dimension"],
        "mode": item["mode"], "target": target, "observed": observed,
        "error": observed - target,
        "count_ok": count_ok, "keyword_ok": keyword_ok, "unique_ok": unique_ok,
        "empty": not text,
        # `bool(text)` is currently subsumed: every item in this dataset requires a keyword, and
        # an empty answer cannot contain one, so the empty response already fails. Measured, not
        # assumed: removing it moved nothing in the fingerprint, which is why the sabotage suite
        # carries no attack on it. It stays because a family without a keyword requirement would
        # make it load-bearing again, and 40 items have a bound an empty answer satisfies.
        "compliant": bool(text) and count_ok and keyword_ok and unique_ok,
        "unwrapped": notes,
        "reasons": reasons,
    }


BUCKETS = ("<=-10", "-9..-5", "-4..-2", "-1", "0", "+1", "+2..+4", "+5..+9", ">=+10")


def bucket(error: int) -> str:
    if error <= -10:
        return "<=-10"
    if error <= -5:
        return "-9..-5"
    if error <= -2:
        return "-4..-2"
    if error == -1:
        return "-1"
    if error == 0:
        return "0"
    if error == 1:
        return "+1"
    if error <= 4:
        return "+2..+4"
    if error <= 9:
        return "+5..+9"
    return ">=+10"


def error_profile(rows: list) -> dict:
    """What the errors look like, which is the part a pass rate destroys."""
    errors = [row["error"] for row in rows]
    misses = [row["error"] for row in rows if not row["count_ok"]]
    relative = [abs(row["error"]) / row["target"] for row in rows if row["target"]]
    counts = {name: 0 for name in BUCKETS}
    for value in errors:
        counts[bucket(value)] += 1
    return {
        "n": len(rows),
        "count_violations": len(misses),
        "off_by_one": sum(1 for value in misses if abs(value) == 1),
        "off_by_one_share_of_misses": round(
            sum(1 for value in misses if abs(value) == 1) / len(misses), 4) if misses else None,
        "over": sum(1 for value in misses if value > 0),
        "under": sum(1 for value in misses if value < 0),
        "mean_error": round(statistics.fmean(errors), 3) if errors else None,
        "median_error": statistics.median(errors) if errors else None,
        "mean_abs_error": round(statistics.fmean(abs(v) for v in errors), 3) if errors else None,
        "median_abs_relative_error": round(statistics.median(relative), 4) if relative else None,
        "histogram": counts,
    }


def score(items: list, responses: dict, ruleset=None, lenient: bool = False) -> dict:
    """Grade a whole run. `responses` maps item id to response text; a missing id is a failure.

    A missing response is graded as an empty one rather than dropped. Dropping it would let a
    system that answered only the easy half of the dataset report the score of the half it liked.
    """
    rows = [grade(item, responses.get(item["id"]), ruleset, lenient) for item in items]
    families = {}
    for row in rows:
        families.setdefault(row["family"], []).append(row)
    def summarise(group):
        compliant = sum(1 for row in group if row["compliant"])
        return {
            "n": len(group),
            "compliant": compliant,
            "rate": round(compliant / len(group), 4) if group else 0.0,
            "count_ok": sum(1 for row in group if row["count_ok"]),
            "keyword_ok": sum(1 for row in group if row["keyword_ok"]),
            "unique_ok": sum(1 for row in group if row["unique_ok"]),
            "empty": sum(1 for row in group if row["empty"]),
            "errors": error_profile(group),
        }
    return {
        "overall": summarise(rows),
        "families": {name: summarise(group) for name, group in sorted(families.items())},
        "rows": rows,
    }
