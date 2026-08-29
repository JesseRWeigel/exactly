"""The counting rules. This file IS the benchmark.

Every constraint in this dataset is a claim about a number, and a number needs a rule before it
is a fact. "Exactly 100 words" is undefined until somebody says whether `state-of-the-art` is one
word or four, whether `3.14` is a word at all, whether a bare emoji counts, and what an em dash
is. "Three sentences" is undefined until somebody says what happens to `Dr. Smith`, to `e.g.`, to
`3.14`, to `1. First item` and to a trailing fragment with no full stop on the end. "Seven
bullets" is undefined until somebody says whether a nested sub-bullet is a bullet and whether a
numbered list is a list of bullets.

Each of those questions has more than one defensible answer, so a benchmark that picks one
silently is grading models on its own tokenizer. This project does three things instead:

  IT WRITES THE RULES DOWN. Each counter here has a `plain` dialect, which is the published one,
  and the text of that dialect is generated FROM THIS FILE'S TABLES by `explain()` below.

  IT PUTS THEM IN THE PROMPT. Every prompt in the dataset carries the rule its answer will be
  checked against, because a model cannot comply with a rule it was not told, and a benchmark
  that hides the rule is measuring telepathy.

  IT MEASURES HOW MUCH THE RULE MATTERS. Every counter also has alternative dialects, each one a
  defensible reading somebody else would have picked, and the report scores the same responses
  under all of them. The spread between them is the honest error bar on every number in the
  leaderboard.

Nothing here is clever. It is written out longhand on purpose, because a counting rule that
cannot be read and disagreed with is not a rule.
"""

from __future__ import annotations

import re
import unicodedata

# Dashes that SEPARATE the tokens on either side of them, unlike the hyphen-minus, which joins.
SEPARATING_DASHES = "—–―−"
ELLIPSIS = "…"
TERMINATORS = ".!?" + ELLIPSIS
CLOSERS = "\"'’”)]}»"

# Abbreviations whose full stop does not end a sentence. Compared case insensitively against the
# run of letters and dots immediately before the stop. A closed list is the honest shape here:
# there is no rule that separates `etc.` from `Ltd.` without one, and pretending otherwise would
# hide the arbitrariness rather than remove it.
ABBREVIATIONS = (
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "rev", "hon", "gen", "col", "sgt",
    "lt", "capt", "messrs", "vs", "etc", "e.g", "i.e", "cf", "al", "approx", "est", "fig", "eq",
    "no", "vol", "ch", "sec", "pp", "ed", "eds", "trans", "inc", "ltd", "co", "corp", "dept",
    "univ", "ave", "rd", "blvd", "apt", "a.m", "p.m", "u.s", "u.k", "u.n", "e.u", "ph.d", "b.a",
    "m.a", "d.c", "min", "max", "sq", "ft", "in", "lb", "oz", "kg", "km",
)

BULLET_MARKER = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+•‣●·]|"
                           r"\d{1,3}[.)]|\(\d{1,3}\)|[a-zA-Z][.)])(?P<gap>[ \t]+)(?=\S)")
DASH_MARKER = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+•‣●·])"
                         r"(?P<gap>[ \t]+)(?=\S)")

DIALECTS = {
    "words": ("plain", "hyphen_split", "whitespace", "alpha_only"),
    "sentences": ("plain", "naive", "newline_breaks", "require_terminator"),
    "bullets": ("plain", "all_levels", "dash_only"),
    "items": ("normalized", "exact", "first_word"),
    "chars": ("codepoints", "no_whitespace", "utf8_bytes", "nfc_codepoints"),
    "lines": ("nonblank", "all_lines", "stripped_all"),
    "paragraphs": ("blank_line", "single_newline", "indent_or_blank"),
}

# The rule set the prompts are written against and the leaderboard is scored under.
PUBLISHED = {
    "words": "plain",
    "sentences": "plain",
    "bullets": "plain",
    "items": "normalized",
    "chars": "codepoints",
    "lines": "nonblank",
    "paragraphs": "blank_line",
}


class UnknownDialect(ValueError):
    """Raised rather than falling back to a default.

    A counter that quietly used `plain` when asked for a dialect it did not have would report
    a sensitivity of zero for that dialect, which is the exact wrong answer: it would look like
    evidence that the rule does not matter.
    """


def _check(dimension: str, dialect: str) -> str:
    if dialect not in DIALECTS[dimension]:
        raise UnknownDialect(f"{dimension} has no dialect named {dialect!r}; it has "
                             f"{', '.join(DIALECTS[dimension])}")
    return dialect


# ---------------------------------------------------------------------------------------------
# words
# ---------------------------------------------------------------------------------------------

def _alnum(token: str) -> bool:
    return any(ch.isalnum() for ch in token)


def _alpha(token: str) -> bool:
    return any(ch.isalpha() for ch in token)


def words(text: str, dialect: str = "plain") -> list:
    """The words of `text`, under one of four defensible readings.

    plain           a whitespace token counts if it holds a letter or a digit, so a hyphenated
                    compound, a contraction, a number and a URL are each ONE word, and a bare
                    symbol or emoji is none. Em and en dashes separate; the hyphen-minus joins.
    hyphen_split    the same, except the hyphen-minus separates too, so `state-of-the-art` is 4.
    whitespace      every whitespace token counts, including a lone dash and a lone emoji.
    alpha_only      plain, except a token needs a LETTER, so `3.14` and `1,000` are not words.
    """
    _check("words", dialect)
    if dialect == "whitespace":
        return text.split()
    prepared = text
    for character in SEPARATING_DASHES + ELLIPSIS:
        prepared = prepared.replace(character, " ")
    if dialect == "hyphen_split":
        prepared = prepared.replace("-", " ")
    tokens = prepared.split()
    keep = _alpha if dialect == "alpha_only" else _alnum
    return [token for token in tokens if keep(token)]


def count_words(text: str, dialect: str = "plain") -> int:
    return len(words(text, dialect))


# ---------------------------------------------------------------------------------------------
# sentences
# ---------------------------------------------------------------------------------------------

def _is_list_marker_stop(text: str, index: int) -> bool:
    """True when the stop at `index` closes a list marker such as `1.` at the head of a line.

    Without this every numbered list item would open a new sentence, so a model asked for three
    sentences in a numbered list would be marked as having written six.
    """
    if text[index] != ".":
        return False
    scan = index - 1
    digits = 0
    while scan >= 0 and text[scan].isdigit():
        scan -= 1
        digits += 1
    if digits == 0:
        return False
    while scan >= 0 and text[scan] in " \t":
        scan -= 1
    return scan < 0 or text[scan] == "\n"


def _preceding_abbreviation(text: str, index: int) -> bool:
    scan = index - 1
    letters = []
    while scan >= 0 and (text[scan].isalpha() or text[scan] == "."):
        letters.append(text[scan])
        scan -= 1
    word = "".join(reversed(letters)).strip(".")
    return bool(word) and word.lower() in ABBREVIATIONS


def _boundaries(text: str, dialect: str) -> list:
    """Indices one past the end of each sentence, under `plain`, `naive` or `newline_breaks`."""
    cuts = []
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "\n" and dialect == "newline_breaks":
            cuts.append(index + 1)
            index += 1
            continue
        if character not in TERMINATORS:
            index += 1
            continue
        run = index
        while run + 1 < length and text[run + 1] in TERMINATORS:
            run += 1
        if dialect == "naive":
            cuts.append(run + 1)
            index = run + 1
            continue
        # plain and newline_breaks share the careful reading below.
        if character == "." and run == index:
            # There is deliberately no separate test for a decimal point here. A stop inside
            # 3.14 is followed by a digit, and a cut already requires whitespace after the stop,
            # so the case is decided further down and a guard for it would be unreachable. That
            # is not a guess: the sabotage suite could not make an explicit decimal guard change
            # any number in the fingerprint, which is what proved it dead and got it removed.
            if _is_list_marker_stop(text, index):
                index += 1
                continue
            if _preceding_abbreviation(text, index):
                index += 1
                continue
        end = run + 1
        while end < length and text[end] in CLOSERS:
            end += 1
        rest = text[end:]
        if rest.strip() == "":
            cuts.append(end)
            break
        if not rest[:1].isspace():
            index = run + 1
            continue
        nxt = rest.lstrip()[:1]
        # A lowercase letter after a stop means the stop was doing something else, most often an
        # abbreviation this list does not carry. Refusing the cut is the conservative reading.
        if nxt.isalpha() and nxt.islower():
            index = run + 1
            continue
        cuts.append(end)
        index = end
    return cuts


def sentences(text: str, dialect: str = "plain") -> list:
    """The sentences of `text`.

    plain               a sentence ends at `.`, `!`, `?` or a horizontal ellipsis, together with
                        any closing quotes or brackets after it. A stop inside a number, a stop
                        closing a list marker such as `1.`, a stop after a known abbreviation and
                        a stop followed by a lowercase letter do not end a sentence. Text after
                        the last terminator counts as a sentence if it contains a word.
    naive               any run of `.!?` ends a sentence, with none of the exceptions.
    newline_breaks      plain, and a line break also ends a sentence.
    require_terminator  plain, except a trailing fragment with no terminator does not count.
    """
    _check("sentences", dialect)
    walk = "plain" if dialect == "require_terminator" else dialect
    cuts = _boundaries(text, walk)
    pieces = []
    start = 0
    for cut in cuts:
        pieces.append((text[start:cut], True))
        start = cut
    if start < len(text):
        pieces.append((text[start:], False))
    kept = []
    for piece, terminated in pieces:
        if not count_words(piece):
            continue
        if dialect == "require_terminator" and not terminated:
            continue
        kept.append(piece.strip())
    return kept


def count_sentences(text: str, dialect: str = "plain") -> int:
    return len(sentences(text, dialect))


# ---------------------------------------------------------------------------------------------
# bullets and list items
# ---------------------------------------------------------------------------------------------

def _indent_width(indent: str) -> int:
    return len(indent.replace("\t", "    "))


def bullet_lines(text: str, dialect: str = "plain") -> list:
    """The lines of `text` that are bullets, as (indent width, marker, body).

    plain        `-`, `*`, `+`, a bullet character, `1.`, `1)`, `(1)` or `a.` followed by a space
                 and some text, indented by fewer than 2 columns, so a nested sub-bullet is not
                 counted as a bullet of the list.
    all_levels   the same markers at any indentation, so sub-bullets count.
    dash_only    only the symbol markers at the top level, so a numbered list is not bullets.
    """
    _check("bullets", dialect)
    pattern = DASH_MARKER if dialect == "dash_only" else BULLET_MARKER
    found = []
    for line in text.split("\n"):
        match = pattern.match(line)
        if not match:
            continue
        width = _indent_width(match.group("indent"))
        if dialect != "all_levels" and width >= 2:
            continue
        found.append((width, match.group("marker"), line[match.end():].strip()))
    return found


def count_bullets(text: str, dialect: str = "plain") -> int:
    return len(bullet_lines(text, dialect))


def item_key(body: str, dialect: str = "normalized") -> str:
    """The form two list items are compared in when deciding whether they are duplicates.

    normalized   casefolded, punctuation dropped, whitespace collapsed, so `Red apples.` and
                 `red apples` are the same item.
    exact        the text after the marker, stripped, compared character for character.
    first_word   the first word only, so `red apple` and `red car` are the same item.
    """
    _check("items", dialect)
    if dialect == "exact":
        return body.strip()
    if dialect == "first_word":
        found = words(body)
        return found[0].casefold() if found else ""
    cleaned = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in body)
    return " ".join(cleaned.split()).casefold()


def duplicate_items(text: str, bullet_dialect: str = "plain", item_dialect: str = "normalized"):
    """The keys that appear more than once, in the order they first repeat."""
    seen = {}
    repeats = []
    for _, _, body in bullet_lines(text, bullet_dialect):
        key = item_key(body, item_dialect)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            repeats.append(key)
    return repeats


# ---------------------------------------------------------------------------------------------
# characters, lines, paragraphs
# ---------------------------------------------------------------------------------------------

def count_chars(text: str, dialect: str = "codepoints") -> int:
    """codepoints: Unicode code points after stripping the ends. no_whitespace: whitespace
    removed. utf8_bytes: the UTF-8 encoding's length. nfc_codepoints: NFC normalised first."""
    _check("chars", dialect)
    stripped = text.strip()
    if dialect == "no_whitespace":
        return len("".join(stripped.split()))
    if dialect == "utf8_bytes":
        return len(stripped.encode("utf-8"))
    if dialect == "nfc_codepoints":
        return len(unicodedata.normalize("NFC", stripped))
    return len(stripped)


def lines(text: str, dialect: str = "nonblank") -> list:
    """nonblank: lines holding at least one word. all_lines: every line of the stripped text,
    blank ones included. stripped_all: every line holding any non-whitespace."""
    _check("lines", dialect)
    if dialect == "all_lines":
        stripped = text.strip("\n")
        return stripped.split("\n") if stripped else []
    found = text.split("\n")
    if dialect == "stripped_all":
        return [line for line in found if line.strip()]
    return [line for line in found if count_words(line)]


def count_lines(text: str, dialect: str = "nonblank") -> int:
    return len(lines(text, dialect))


def paragraphs(text: str, dialect: str = "blank_line") -> list:
    """blank_line: blocks separated by one or more blank lines, each holding a word.
    single_newline: every line holding a word is a paragraph.
    indent_or_blank: blank_line, and an indented line also opens a new paragraph."""
    _check("paragraphs", dialect)
    if dialect == "single_newline":
        return [line.strip() for line in text.split("\n") if count_words(line)]
    blocks = []
    current = []
    for line in text.split("\n"):
        blank = not line.strip()
        indented = (dialect == "indent_or_blank" and current
                    and line[:1] in (" ", "\t") and bool(line.strip()))
        if blank or indented:
            if current:
                blocks.append("\n".join(current))
                current = []
            if indented:
                current.append(line)
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return [block.strip() for block in blocks if count_words(block)]


def count_paragraphs(text: str, dialect: str = "blank_line") -> int:
    return len(paragraphs(text, dialect))


COUNTERS = {
    "words": count_words,
    "sentences": count_sentences,
    "bullets": count_bullets,
    "chars": count_chars,
    "lines": count_lines,
    "paragraphs": count_paragraphs,
}


def count(dimension: str, text: str, ruleset=None) -> int:
    """The count of `dimension` in `text` under a rule set, defaulting to the published one."""
    ruleset = PUBLISHED if ruleset is None else ruleset
    if dimension not in COUNTERS:
        raise UnknownDialect(f"there is no counter for {dimension!r}")
    return COUNTERS[dimension](text, ruleset.get(dimension, PUBLISHED[dimension]))


# ---------------------------------------------------------------------------------------------
# the rules, in the words the model is shown
# ---------------------------------------------------------------------------------------------

EXPLANATIONS = {
    "words": (
        "Split the answer on whitespace. A token counts as one word if it contains at least one"
        " letter or digit.",
        "A hyphenated compound such as state-of-the-art is ONE word.",
        "A contraction such as don't is ONE word.",
        "A number such as 3.14 or 1,000 is ONE word, and so is a URL.",
        "A token with no letter or digit in it, such as a lone dash or an emoji, is NOT a word.",
        "An em dash or an en dash separates the tokens on either side of it. A hyphen does not.",
    ),
    "sentences": (
        "A sentence ends at a full stop, an exclamation mark, a question mark or an ellipsis,"
        " together with any closing quote or bracket that follows it.",
        "A full stop inside a number such as 3.14 does not end a sentence.",
        "A full stop after a common abbreviation such as Dr. or e.g. does not end a sentence.",
        "A full stop closing a list marker such as 1. at the start of a line does not end a"
        " sentence.",
        "A full stop followed by a lowercase letter does not end a sentence.",
        "Text after the last terminator counts as a sentence if it contains a word, so a"
        " trailing fragment with no full stop still counts.",
    ),
    "bullets": (
        "A bullet is a line beginning with -, *, +, a bullet character, or a marker such as 1.,"
        " 1) or a), followed by a space and some text.",
        "The line must be indented by fewer than 2 columns, so a nested sub-bullet does NOT"
        " count as a bullet of the list.",
        "A numbered list DOES count as bullets.",
    ),
    "items": (
        "Two items are the same item if they match after casefolding, dropping punctuation and"
        " collapsing whitespace, so Red apples. and red apples are ONE item repeated.",
    ),
    "chars": (
        "Characters are Unicode code points, counted after removing whitespace from the start"
        " and the end of the answer.",
        "Spaces between words DO count. Punctuation counts.",
    ),
    "lines": (
        "A line counts if it contains at least one word. Blank lines do not count.",
    ),
    "paragraphs": (
        "Paragraphs are separated by one or more blank lines.",
        "A block counts as a paragraph if it contains at least one word.",
    ),
}


def explain(dimension: str, unique: bool = False) -> str:
    """The published rule for one dimension, as it appears inside every prompt using it."""
    parts = list(EXPLANATIONS[dimension])
    if unique:
        parts += list(EXPLANATIONS["items"])
    return "\n".join("- " + part for part in parts)


def ruleset_from(overrides=None) -> dict:
    """A full rule set: the published one with named dialects swapped in."""
    made = dict(PUBLISHED)
    for dimension, dialect in (overrides or {}).items():
        if dimension not in DIALECTS:
            raise UnknownDialect(f"there is no dimension named {dimension!r}")
        made[dimension] = _check(dimension, dialect)
    return made
