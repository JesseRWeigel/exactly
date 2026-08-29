"""One canonical number for everything this project claims, so a sabotage has something to move.

WHAT IS IN IT, and why each part is there:

  THE PROBE CORPUS. Forty short texts chosen because each one sits on a decision some counter has
  to make: an abbreviation, a decimal, a nested bullet, a numbered list, a combining accent, an em
  dash, a trailing fragment. Every counter is run over every probe under every dialect. This is
  the part that makes the measurement WIDE. A leaderboard alone is a narrow measurement: an
  off-by-one in the line counter moves it by a fraction of a point on one family and can round
  away, while here it changes an integer that is hashed.

  THE DATASET. The prompt digest, so a change to a prompt or to the rule text inside a prompt is
  caught even though no score moves.

  THE BASELINES. Every baseline's rate, count, keyword and uniqueness tallies, its error
  histogram, and its per-family rates. This is what catches a grader that has stopped checking
  something.

  THE SENSITIVITY. The per-dimension spread for the reference and approximate baselines, so a
  dialect that has quietly become a copy of the published one shows up.

  A PARTIALLY ANSWERED RUN. Every baseline answers all 500, so nothing else here can tell the
  difference between counting an unanswered item as a failure and quietly dropping it. That case
  is constructed rather than waited for.

WHAT IS DELIBERATELY NOT IN IT: any recorded model response. Sampling is not reproducible, a
fixture can be re-recorded on a busy day, and a fingerprint that moved when a model was re-run
would make every sabotage pass gate 2 for free. The deterministic part of this project is the
prompt set, the counting rules and the grader, and that is exactly what is hashed. The model
fixtures are checked by `verify.sh` separately, against their own committed digests.

No absolute path, no timestamp and no host detail is hashed, for the same reason: the null
control has to reproduce the fingerprint byte for byte from a differently named directory.
"""

from __future__ import annotations

import hashlib
import json

from . import baselines, generate, grade, report, rules

# Each probe names the decision it sits on. The label is hashed too, so moving a probe onto a
# different case without renaming it is itself a change.
PROBES = (
    ("plain prose", "The bread rose overnight. It smelled of yeast."),
    ("title abbreviation", "Dr. Smith arrived. He waited."),
    ("eg abbreviation", "Some books, e.g. the old ones, are good."),
    ("ie abbreviation", "The result, i.e. the number, was wrong. Then it was right."),
    ("decimal number", "It took 3.5 hours. Then it stopped."),
    ("thousands separator", "There were 1,000 of them in the room."),
    ("numbered list", "1. First thing.\n2. Second thing.\n3. Third thing."),
    ("dash bullets", "- one\n- two\n- three"),
    ("nested bullet", "- one\n  - nested\n- two"),
    ("tab nested bullet", "- one\n\t- nested\n- two"),
    ("paren markers", "(1) one\nb) two\n• three"),
    ("marker with no body", "- \n- yes"),
    ("marker with no space", "-nospace\n- yes"),
    ("hyphenated compound", "A state-of-the-art design won."),
    ("em dash", "one—two three"),
    ("en dash range", "The years 1999–2003 were quiet."),
    ("contraction", "Don't stop now."),
    ("url", "See https://example.com/a/b for more."),
    ("lone symbol", "a + b = c"),
    ("emoji", "good \U0001f600 morning"),
    # Written as escapes. Two literals that differ only in Unicode normalisation look identical
    # in an editor, and a probe corpus whose two accent cases were secretly the same text would
    # report a reassuring zero for the one dialect it exists to exercise.
    ("combining accent", "cafe\u0301 au lait"),
    ("precomposed accent", "caf\u00e9 au lait"),
    ("trailing fragment", "One sentence here. A fragment with no stop"),
    ("closing quote", 'He said "stop now." Then he left.'),
    ("ellipsis", "It trailed off… Then it resumed."),
    ("terminator run", "Really?! Yes."),
    ("lowercase after stop", "Ordered from acme. inc and shipped."),
    ("blank lines", "one\n\ntwo\n   \nthree"),
    ("punctuation line", "one\n---\ntwo"),
    ("two paragraphs", "one\nstill one\n\ntwo"),
    ("indented block", "one\n    indented\n\ntwo"),
    ("many blank lines", "one\n\n\n\ntwo"),
    ("code fence", "```\nyeast makes the bread rise\n```"),
    ("preamble line", "Here is the answer:\nyeast makes the bread rise"),
    ("self reported count", "yeast makes the bread rise\n(5 words)"),
    ("repeated item", "- Red apples.\n- red apples\n- red cars"),
    ("leading whitespace", "   padded on both ends   "),
    ("empty", ""),
    ("whitespace only", "   \n  \t "),
    ("single word", "yeast"),
)

# The baselines whose rule sensitivity is hashed. The reference is the control and must be perfect
# under the published rules; approximate is the one with a spread of errors, so a change to the
# error machinery moves it.
SENSITIVITY_SYSTEMS = ("reference", "approximate")


def probe_counts() -> dict:
    """Every counter, over every probe, under every dialect."""
    made = {}
    for label, text in PROBES:
        entry = {}
        for dimension, dialects in sorted(rules.DIALECTS.items()):
            if dimension == "items":
                entry["items"] = {
                    dialect: rules.duplicate_items(text, "plain", dialect)
                    for dialect in dialects}
                continue
            entry[dimension] = {dialect: rules.COUNTERS[dimension](text, dialect)
                                for dialect in dialects}
        entry["keyword_yeast"] = grade.keyword_present(text, "yeast")
        entry["unwrapped"] = grade.unwrap(text)[1]
        made[label] = entry
    return made


def baseline_scores(items: list) -> dict:
    made = {}
    for name in ("reference",) + baselines.NAMES:
        scored = grade.score(items, baselines.responses(name, items))
        made[name] = {
            "overall": scored["overall"],
            "families": {family: {"rate": row["rate"], "count_ok": row["count_ok"],
                                  "keyword_ok": row["keyword_ok"], "unique_ok": row["unique_ok"],
                                  "empty": row["empty"], "errors": row["errors"]}
                         for family, row in scored["families"].items()},
        }
    return made


def partial_coverage(items: list) -> dict:
    """Grade a system that answered only part of the dataset.

    Here because a sabotage that DROPPED unanswered items from the score could not be caught
    without it. Every baseline answers all 500, so on that corpus the difference between counting
    a missing answer as a failure and ignoring it is invisible, and the sabotage was inert for
    want of a case rather than for want of a bug. This is the corpus being too clean, and the fix
    is a case that exercises the code, not a smaller sabotage list.
    """
    answers = baselines.responses("reference", items)
    for item in items[::5]:
        answers.pop(item["id"], None)
    scored = grade.score(items, answers)
    return {"answered": len(answers), "of": len(items), "overall": scored["overall"]}


def payload() -> dict:
    """Everything hashed, as plain data, so a human can diff two runs and see what moved."""
    items, meta = generate.load()
    return {
        "dataset": {
            "count": meta["count"],
            "seed": meta["seed"],
            "prompts_sha256": meta["prompts_sha256"],
            # The digest the CODE produces today, next to the one the committed manifest states.
            # Without this the prompt builder and the manifest builder could both be broken and
            # nothing hashed here would move, because everything else reads the committed file.
            "rebuilt_prompts_sha256": generate.manifest(generate.build())["prompts_sha256"],
            "published_rules": meta["published_rules"],
            "dialects": meta["dialects"],
            "families": {name: row["n"] for name, row in sorted(meta["families"].items())},
        },
        "probes": probe_counts(),
        "baselines": baseline_scores(items),
        "partial_coverage": partial_coverage(items),
        "sensitivity": {
            name: report.sensitivity_for(items, baselines.responses(name, items))
            for name in SENSITIVITY_SYSTEMS
        },
        "explanations": {dimension: rules.explain(dimension)
                         for dimension in sorted(rules.EXPLANATIONS)},
    }


def canonical(data=None) -> str:
    return json.dumps(payload() if data is None else data, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))


def digest(data=None) -> str:
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()
