"""Build an answer that satisfies a counting constraint exactly. The inverse of `rules.py`.

This exists for two reasons that are worth separating.

  IT IS THE CONTROL. A benchmark whose grader cannot be scored 100 by anything is not a
  benchmark, it is a bug. `baselines.reference` composes an answer for every one of the 500
  prompts and the build refuses to ship if a single one is graded non-compliant, so the harness
  is proved able to accept a correct answer before any model is asked for one.

  IT IS THE PROOF THE RULES ARE CONSTRUCTIVE. A counting rule you can check but cannot write to
  is a rule nobody can follow. Every dialect question in `rules.py` had to be answered here too,
  in the opposite direction, and an answer that could not be built exactly would have meant the
  rule was underspecified.

The reference answers deliberately carry the shapes the published rules make decisions about: an
abbreviation, a decimal number, a numbered list marker, a nested sub-bullet, a blank line. That
is not decoration. It is what makes the reference score BELOW 100 under the alternative dialects,
which is the clearest possible statement that the rule choice is doing real work.
"""

from __future__ import annotations

import random

from . import corpus, rules

# Filler grouped by length, so a character target can be met exactly rather than approximately.
BY_LENGTH = {}
for _word in corpus.FILLER:
    BY_LENGTH.setdefault(len(_word), []).append(_word)
BY_LENGTH = {length: tuple(sorted(set(found))) for length, found in BY_LENGTH.items()}


def _rng(item_id: str, offset: int = 0) -> random.Random:
    """A generator seeded from the item's own id, so an answer never depends on call order."""
    return random.Random(f"{item_id}/{offset}")


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def words_answer(n: int, keyword: str, item_id: str) -> str:
    """Exactly `n` words under the published word rule, containing `keyword`."""
    if n < 1:
        raise ValueError("a word target below one cannot contain the keyword")
    rng = _rng(item_id, 1)
    chosen = [keyword] + [rng.choice(corpus.FILLER) for _ in range(n - 1)]
    if n > 3:
        chosen[0], chosen[2] = chosen[2], chosen[0]
    pieces = []
    for index, word in enumerate(chosen):
        if index and index % 11 == 0:
            pieces.append(word + ".")
        else:
            pieces.append(word)
    text = " ".join(pieces)
    return _cap(text).rstrip(".") + "."


def sentences_answer(n: int, keyword: str, item_id: str) -> str:
    """Exactly `n` sentences under the published sentence rule, containing `keyword`."""
    rng = _rng(item_id, 2)
    stems = list(corpus.SENTENCE_STEMS)
    rng.shuffle(stems)
    made = []
    for index in range(n):
        stem = stems[index % len(stems)].format(keyword=keyword)
        if index >= len(stems):
            stem += " " + rng.choice(BY_LENGTH[6]) + " " + rng.choice(BY_LENGTH[5])
        made.append(_cap(stem) + ".")
    return " ".join(made)


def bullets_answer(n: int, keyword: str, item_id: str, nested: bool = True,
                   numbered: bool = False) -> str:
    """Exactly `n` top-level bullets, with nested sub-bullets that must NOT be counted."""
    rng = _rng(item_id, 3)
    stems = list(corpus.ITEM_STEMS)
    rng.shuffle(stems)
    out = []
    for index in range(n):
        body = stems[index % len(stems)].format(keyword=keyword)
        if index >= len(stems):
            body += " " + rng.choice(BY_LENGTH[7])
        marker = f"{index + 1}." if numbered else "-"
        out.append(f"{marker} {body}.")
        if nested and index == 0 and n > 1:
            out.append(f"  - {rng.choice(BY_LENGTH[8])} {rng.choice(BY_LENGTH[6])}.")
    return "\n".join(out)


def unique_items_answer(n: int, keyword: str, item_id: str) -> str:
    """Exactly `n` bullets, no two of which are the same item under the published item rule."""
    rng = _rng(item_id, 4)
    stems = list(corpus.ITEM_STEMS)
    rng.shuffle(stems)
    out = []
    for index in range(n):
        body = stems[index % len(stems)].format(keyword=keyword)
        if index >= len(stems):
            body += " " + BY_LENGTH[8][index % len(BY_LENGTH[8])]
        out.append(f"- {body}.")
    return "\n".join(out)


def lines_answer(n: int, keyword: str, item_id: str) -> str:
    """Exactly `n` lines holding a word, with a blank line the published rule ignores."""
    rng = _rng(item_id, 5)
    stems = list(corpus.ITEM_STEMS)
    rng.shuffle(stems)
    out = []
    for index in range(n):
        body = stems[index % len(stems)].format(keyword=keyword)
        if index >= len(stems):
            body += " " + rng.choice(BY_LENGTH[6])
        out.append(_cap(body) + ".")
        if index == 0 and n > 2:
            out.append("")
    return "\n".join(out)


def paragraphs_answer(n: int, keyword: str, item_id: str) -> str:
    """Exactly `n` paragraphs, each of two lines, so a per-line reading would say 2n."""
    rng = _rng(item_id, 6)
    stems = list(corpus.SENTENCE_STEMS)
    rng.shuffle(stems)
    blocks = []
    for index in range(n):
        first = _cap(stems[(2 * index) % len(stems)].format(keyword=keyword)) + "."
        second = _cap(stems[(2 * index + 1) % len(stems)].format(keyword=keyword)) + "."
        blocks.append(first + "\n" + second)
    return "\n\n".join(blocks)


def chars_answer(n: int, keyword: str, item_id: str) -> str:
    """Exactly `n` code points after stripping, containing `keyword`.

    Padding is chosen BY LENGTH rather than at random, because a target has to be hit on the nose
    and a greedy fill leaves a gap that only a word of one exact length can close. The available
    word lengths run from 1 to 8 with no gaps, which is what makes the closing step always
    possible: whenever the remainder is larger than 8 a word is chosen that leaves at least one
    character for the next one, and whenever it is 8 or less it is closed in a single step.
    """
    opener = _cap(keyword)
    if n < len(opener) + 1:
        raise ValueError(f"{n} characters is too few to hold {keyword!r} and a full stop")
    rng = _rng(item_id, 7)
    lengths = sorted(BY_LENGTH)
    shortest, longest = lengths[0], lengths[-1]
    text = opener
    while True:
        remaining = n - len(text) - 1                    # what is left before the full stop
        if remaining <= 0:
            break
        need = remaining - 1                             # a space, then a word of this length
        if need == 0:
            # Only reachable for a target two longer than the keyword, which no dataset item
            # is. A space before the stop is the one legal way to spend a single character.
            text += " "
            break
        if need in BY_LENGTH:
            text += " " + rng.choice(BY_LENGTH[need])
            break
        text += " " + rng.choice(BY_LENGTH[min(longest, need - 1 - shortest)])
    text += "."
    if len(text) != n:                                   # pragma: no cover, the loop is exact
        raise AssertionError(f"composed {len(text)} characters and wanted {n}")
    return text


BUILDERS = {
    "words": lambda item, target: words_answer(target, item["keyword"], item["id"]),
    "sentences": lambda item, target: sentences_answer(target, item["keyword"], item["id"]),
    "chars": lambda item, target: chars_answer(target, item["keyword"], item["id"]),
    "lines": lambda item, target: lines_answer(target, item["keyword"], item["id"]),
    "paragraphs": lambda item, target: paragraphs_answer(target, item["keyword"], item["id"]),
}


def answer(item: dict, target=None) -> str:
    """A compliant answer for one dataset item, or for a deliberately wrong target."""
    target = item["target"] if target is None else target
    if item["dimension"] == "bullets":
        if item["unique"]:
            return unique_items_answer(target, item["keyword"], item["id"])
        numbered = int(item["id"].rsplit("-", 1)[1]) % 3 == 0
        return bullets_answer(target, item["keyword"], item["id"], numbered=numbered)
    return BUILDERS[item["dimension"]](item, target)


def observed(item: dict, text: str, ruleset=None) -> int:
    """What the published rules say this answer contains, for the dimension the item asks about."""
    return rules.count(item["dimension"], text, ruleset)
