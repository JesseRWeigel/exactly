"""Systems that answer without a model, because a benchmark with no baseline is a file.

What each one is for:

  reference        composes a correct answer from the rules themselves. It MUST score 100. A
                   grader nothing can satisfy is broken, and every other number on the board is
                   read against this one.
  off_by_one       the reference, one unit out in the direction that breaks the constraint. It
                   MUST score 0 on the count. A grader that lets this through is not counting.
  blank            nothing at all. MUST score 0, which is how the empty response is proved to be
                   a failure rather than a vacuous pass.
  ignore           one fixed paragraph, the same for every prompt, written about nothing in
                   particular. This is the floor: what a system scores by not reading the
                   constraint at all.
  filler           the requested number of the word `item`, and nothing else. This is the number
                   that matters most in the whole report, and it is deliberately unflattering to
                   the benchmark: counting is MECHANICAL, and a program that understands nothing
                   satisfies the count every time. It fails only on the required keyword.
  filler_keyword   the same trick with the keyword dropped in, so it satisfies everything the
                   grader checks while saying nothing at all. Its score is the honest ceiling on
                   what compliance means here.
  approximate      the reference, displaced by a deterministic pseudo-random amount that scales
                   with the target. It stands in for a system that is roughly right and never
                   exact, and it is what proves the error distribution machinery reports a shape
                   rather than a constant.
"""

from __future__ import annotations

import hashlib

from . import compose, rules

IGNORED_PARAGRAPH = (
    "There is more to say about this than fits in a short reply, and most of it depends on "
    "which part you care about. The short version is that the pieces fit together in a way "
    "that rewards a careful look. Anyone who has spent time with it will tell you the same.")

NAMES = ("blank", "ignore", "filler", "filler_keyword", "approximate", "off_by_one")


def _jitter(item_id: str, target: int) -> int:
    """A deterministic displacement, roughly proportional to the target and never zero.

    Seeded from the item id rather than from a shared generator, so a baseline's answer does not
    depend on how many items were scored before it.
    """
    digest = hashlib.sha256(item_id.encode()).digest()
    span = max(1, round(target * 0.15))
    step = (digest[0] % (2 * span)) - span
    if step == 0:
        step = 1 if digest[1] % 2 else -1
    return step


def _filler_answer(item: dict, keyword=None) -> str:
    """The requested count of a filler unit, with no thought behind it whatsoever."""
    target, dimension = item["target"], item["dimension"]
    word = "item"
    if dimension == "words":
        pieces = [word] * target
        if keyword and target:
            pieces[0] = keyword
        return " ".join(pieces)
    if dimension == "sentences":
        pieces = [f"{word.capitalize()} {index + 1}." for index in range(target)]
        if keyword and target:
            pieces[0] = f"{keyword.capitalize()} 1."
        return " ".join(pieces)
    if dimension == "bullets":
        pieces = [f"- {word} {index + 1}" for index in range(target)]
        if keyword and target:
            pieces[0] = f"- {keyword} 1"
        return "\n".join(pieces)
    if dimension == "lines":
        pieces = [f"{word} {index + 1}" for index in range(target)]
        if keyword and target:
            pieces[0] = f"{keyword} 1"
        return "\n".join(pieces)
    if dimension == "paragraphs":
        pieces = [f"{word} {index + 1}" for index in range(target)]
        if keyword and target:
            pieces[0] = f"{keyword} 1"
        return "\n\n".join(pieces)
    if dimension == "chars":
        if not keyword:
            return "a" * target
        head = keyword.capitalize()
        if target < len(head) + 2:
            return "a" * target
        return head + " " + "a" * (target - len(head) - 1)
    raise ValueError(f"no filler for {dimension!r}")


def _wrong_target(item: dict) -> int:
    """One unit out, in whichever direction the item's mode makes wrong."""
    if item["mode"] == "at_least":
        return max(1, item["target"] - 1)
    return item["target"] + 1


def answer(name: str, item: dict) -> str:
    if name == "reference":
        return compose.answer(item)
    if name == "blank":
        return ""
    if name == "ignore":
        return IGNORED_PARAGRAPH
    if name == "filler":
        return _filler_answer(item)
    if name == "filler_keyword":
        return _filler_answer(item, item["keyword"])
    if name == "off_by_one":
        return compose.answer(item, _wrong_target(item))
    if name == "approximate":
        target = max(1, item["target"] + _jitter(item["id"], item["target"]))
        if item["dimension"] == "chars":
            target = max(target, len(item["keyword"]) + 2)
        return compose.answer(item, target)
    raise ValueError(f"no such baseline: {name!r}")


def responses(name: str, items: list) -> dict:
    return {item["id"]: answer(name, item) for item in items}


def run(items: list, names=None, ruleset=None, lenient: bool = False) -> dict:
    from . import grade
    names = tuple(names) if names else ("reference",) + NAMES
    made = {}
    for name in names:
        scored = grade.score(items, responses(name, items), ruleset, lenient)
        made[name] = {"overall": scored["overall"],
                      "families": {family: row for family, row in scored["families"].items()}}
    return made
