#!/usr/bin/env python3
"""Recount everything from the committed data files, sharing no code with the thing it checks.

A validator that imports the code it validates inherits that code's bugs and reports clean on
output that is not. So this file imports nothing from `exactly`, and it proves that rather than
asserting it: `import_graph()` parses its own source with `ast`, follows every local import it
finds, and fails if `exactly` appears anywhere in the transitive graph. Grep would not do. A grep
is satisfied by a comment mentioning the package and blind to
`importlib.import_module("exactly.rules")`, and both of those cases sit in `scripts/probes/` as
files this checker's own walker is required to accept and refuse. Each probe declares the verdict
it must get on its first line, and the probes are parsed, never executed, which is why a probe
can contain an import that would fail if it ever ran.

The counters below are a second implementation of the published rules, written from the rule text
rather than from the first implementation. Where `exactly.rules` walks the string index by index,
this drives off `re.finditer` and an explicit character machine. Two implementations that agree
are evidence; one implementation called twice is not.

What it recomputes, all of it from files in git and none of it by calling the package:

  the reference control      500 composed answers, every one of which must be compliant
  the off-by-one control     500 answers one unit out, none of which may satisfy the count
  the filler controls        the count is mechanical, so `filler` must hit every count and no
                             keyword, and `filler_keyword` must satisfy everything
  every recorded model       four separate tallies, recounted, against what the leaderboard claims
  the words sensitivity      the spread between the published word rule and `hyphen_split`

Exit code 0 means every recount agreed. Any disagreement is printed with both numbers and exits 1.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE_UNDER_TEST = "exactly"

# --------------------------------------------------------------------------------------------
# the import graph, walked with ast rather than trusted
# --------------------------------------------------------------------------------------------

class ImportLeak(RuntimeError):
    """The checker, or something it imports, reaches into the package under test."""


def _imported_names(tree: ast.AST) -> list:
    """Every module name this source could import, including the dynamic spellings.

    `import a.b`, `from a.b import c`, `importlib.import_module("a.b")` and `__import__("a.b")`
    all count. A relative `from . import x` is resolved against the file's own directory by the
    caller, which is what makes the walk transitive.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append("." * node.level + (node.module or ""))
            elif node.module:
                found.append(node.module)
        elif isinstance(node, ast.Call):
            target = node.func
            name = None
            if isinstance(target, ast.Attribute) and target.attr == "import_module":
                name = "importlib.import_module"
            elif isinstance(target, ast.Name) and target.id == "__import__":
                name = "__import__"
            if name and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                found.append(node.args[0].value)
            elif name:
                found.append("<dynamic import with a computed name>")
    return found


def import_graph(start: pathlib.Path) -> dict:
    """{file: [module names]} for `start` and every local module it can reach."""
    seen = {}
    queue = [pathlib.Path(start).resolve()]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        names = _imported_names(ast.parse(path.read_text(encoding="utf-8"), str(path)))
        seen[path] = names
        for name in names:
            if name.startswith("."):
                continue
            head = name.split(".")[0]
            for candidate in (path.parent / (head + ".py"), path.parent / head / "__init__.py"):
                if candidate.exists():
                    queue.append(candidate.resolve())
    return seen


def assert_no_package_import(start: pathlib.Path) -> dict:
    graph = import_graph(start)
    guilty = []
    for path, names in sorted(graph.items()):
        for name in names:
            if name == PACKAGE_UNDER_TEST or name.startswith(PACKAGE_UNDER_TEST + "."):
                guilty.append(f"{path.name} imports {name}")
            if name.startswith("<dynamic"):
                guilty.append(f"{path.name} imports a computed module name, which cannot be "
                              f"cleared by reading the source")
    if guilty:
        raise ImportLeak("; ".join(guilty))
    return graph


# --------------------------------------------------------------------------------------------
# a second implementation of the published counting rules
# --------------------------------------------------------------------------------------------

SPLITTING = "—–―−…"      # em, en, horizontal bar, minus, ellipsis
TERMINATOR_RUN = re.compile(r"[.!?…]+")
CLOSING = set("\"'’”)]}»")
ABBREVIATION_TAIL = re.compile(r"([A-Za-z](?:\.[A-Za-z])*|[A-Za-z]+)\.$")
LIST_MARKER_STOP = re.compile(r"(?:^|\n)[ \t]*\d{1,3}\.$")
SYMBOL_MARKERS = "-*+•‣●·"

# Transcribed from the rule text, not imported. If the two lists ever disagree the checker will
# say so on any corpus that uses the difference, which is the point of writing it out twice.
KNOWN_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "rev", "hon", "gen", "col", "sgt",
    "lt", "capt", "messrs", "vs", "etc", "e.g", "i.e", "cf", "al", "approx", "est", "fig", "eq",
    "no", "vol", "ch", "sec", "pp", "ed", "eds", "trans", "inc", "ltd", "co", "corp", "dept",
    "univ", "ave", "rd", "blvd", "apt", "a.m", "p.m", "u.s", "u.k", "u.n", "e.u", "ph.d", "b.a",
    "m.a", "d.c", "min", "max", "sq", "ft", "in", "lb", "oz", "kg", "km",
}


def count_words(text: str) -> int:
    """Published word rule, by a character machine rather than by `str.split`."""
    total = 0
    has_alnum = False
    inside = False
    for character in text:
        if character.isspace() or character in SPLITTING:
            if inside and has_alnum:
                total += 1
            inside = False
            has_alnum = False
            continue
        inside = True
        if character.isalnum():
            has_alnum = True
    if inside and has_alnum:
        total += 1
    return total


def count_words_dialect(text: str, dialect: str) -> int:
    """All four published word readings, for the sensitivity recount.

    `plain` is the machine above. `hyphen_split` feeds it text with the hyphens turned into
    spaces. `whitespace` counts every token. `alpha_only` demands a letter rather than any
    alphanumeric, so a bare number stops being a word.
    """
    if dialect == "plain":
        return count_words(text)
    if dialect == "hyphen_split":
        return count_words(text.replace("-", " "))
    prepared = text
    for character in SPLITTING:
        prepared = prepared.replace(character, " ")
    tokens = prepared.split()
    if dialect == "whitespace":
        return len(tokens)
    if dialect == "alpha_only":
        return sum(1 for token in tokens if any(c.isalpha() for c in token))
    raise ValueError(f"no such word dialect here: {dialect!r}")


def _cut_points(text: str) -> list:
    """Where sentences end, driven by `re.finditer` over runs of terminators."""
    cuts = []
    for match in TERMINATOR_RUN.finditer(text):
        start, stop = match.span()
        if cuts and start < cuts[-1]:
            continue
        if match.group() == ".":
            before = text[:start]
            # No decimal test, for the same reason `exactly/rules.py` has none: a stop inside a
            # number is followed by a digit and the whitespace requirement below already refuses
            # the cut. Both implementations dropped it after the sabotage suite showed it inert.
            if LIST_MARKER_STOP.search(before + "."):
                continue
            tail = ABBREVIATION_TAIL.search(before + ".")
            if tail and tail.group(1).lower().strip(".") in KNOWN_ABBREVIATIONS:
                continue
        end = stop
        while end < len(text) and text[end] in CLOSING:
            end += 1
        rest = text[end:]
        if not rest.strip():
            cuts.append(end)
            break
        if not rest[:1].isspace():
            continue
        following = rest.lstrip()[:1]
        if following.isalpha() and following.islower():
            continue
        cuts.append(end)
    return cuts


def count_sentences(text: str) -> int:
    cuts = _cut_points(text)
    pieces = []
    start = 0
    for cut in cuts:
        pieces.append(text[start:cut])
        start = cut
    if start < len(text):
        pieces.append(text[start:])
    return sum(1 for piece in pieces if count_words(piece))


def _bullet_body(line: str):
    """(indent width, body) if `line` opens a bullet under the published rule, else None."""
    position = 0
    width = 0
    while position < len(line) and line[position] in " \t":
        width += 4 if line[position] == "\t" else 1
        position += 1
    rest = line[position:]
    marker = None
    if rest[:1] in tuple(SYMBOL_MARKERS):
        marker = rest[:1]
    else:
        digits = re.match(r"\d{1,3}[.)]", rest)
        parens = re.match(r"\(\d{1,3}\)", rest)
        letter = re.match(r"[a-zA-Z][.)]", rest)
        for candidate in (digits, parens, letter):
            if candidate:
                marker = candidate.group()
                break
    if marker is None:
        return None
    after = rest[len(marker):]
    gap = 0
    while gap < len(after) and after[gap] in " \t":
        gap += 1
    if gap == 0 or gap >= len(after):
        return None
    return width, after[gap:].strip()


def bullet_bodies(text: str) -> list:
    found = []
    for line in text.split("\n"):
        parsed = _bullet_body(line)
        if parsed and parsed[0] < 2:
            found.append(parsed[1])
    return found


def count_bullets(text: str) -> int:
    return len(bullet_bodies(text))


def has_duplicate_items(text: str) -> bool:
    keys = []
    for body in bullet_bodies(text):
        cleaned = []
        for character in body:
            cleaned.append(character if (character.isalnum() or character.isspace()) else " ")
        keys.append(" ".join("".join(cleaned).split()).casefold())
    return len(keys) != len(set(keys))


def count_chars(text: str) -> int:
    return len(text.strip())


def count_lines(text: str) -> int:
    return sum(1 for line in text.split("\n") if count_words(line))


def count_paragraphs(text: str) -> int:
    total = 0
    block = []
    for line in text.split("\n"):
        if line.strip():
            block.append(line)
            continue
        if block:
            total += 1 if count_words("\n".join(block)) else 0
            block = []
    if block:
        total += 1 if count_words("\n".join(block)) else 0
    return total


COUNTERS = {"words": count_words, "sentences": count_sentences, "bullets": count_bullets,
            "chars": count_chars, "lines": count_lines, "paragraphs": count_paragraphs}


def keyword_present(text: str, keyword: str) -> bool:
    """Whole word, case insensitive, with the hyphen AND the separating dashes splitting tokens.

    The first version of this split on whitespace and the ASCII hyphen only, and the cross-check
    against the package caught it on three real model answers out of five hundred. Two of the
    three read `...element---the tensioned strands of **horsehair**---is...`, with em dashes and
    markdown bold around the required word. Splitting on whitespace alone leaves `**horsehair**`
    glued to the dash and to the word after it, so the token cleans down to `horsehairis` and the
    keyword goes missing. The published rule says an em dash separates the tokens on either side
    of it, so it has to separate here too. The three answers were compliant and the independent
    recount was calling them failures.
    """
    wanted = keyword.casefold()
    prepared = unicodedata.normalize("NFC", text)
    for character in SPLITTING:
        prepared = prepared.replace(character, " ")
    for token in re.split(r"[\s\-]+", prepared):
        cleaned = "".join(character for character in token if character.isalnum()).casefold()
        if cleaned == wanted:
            return True
    return False


def compliant(item: dict, response: str) -> bool:
    text = (response or "").strip()
    if not text:
        return False
    observed = COUNTERS[item["dimension"]](text)
    target = item["target"]
    mode = item["mode"]
    if mode == "exact" and observed != target:
        return False
    if mode == "at_most" and observed > target:
        return False
    if mode == "at_least" and observed < target:
        return False
    if not keyword_present(text, item["keyword"]):
        return False
    if item["unique"] and has_duplicate_items(text):
        return False
    return True


def count_ok(item: dict, response: str) -> bool:
    """Whether the COUNT satisfies the constraint, and nothing else.

    An empty answer is not special here, and that matters. Under an upper bound, zero of anything
    satisfies the count, so the empty response passes this and fails `compliant` on the keyword.
    Reporting the two separately is the point: the `blank` baseline satisfying the count on 40 of
    the 500 items is how the leaderboard shows that `no more than 4 sentences` is satisfiable by
    silence. The first version of this function returned False for an empty answer, which folded
    emptiness into the count verdict and disagreed with the package on exactly those 40 rows.
    """
    text = (response or "").strip()
    observed = COUNTERS[item["dimension"]](text)
    if item["mode"] == "exact":
        return observed == item["target"]
    if item["mode"] == "at_most":
        return observed <= item["target"]
    return observed >= item["target"]


# --------------------------------------------------------------------------------------------
# the recounts
# --------------------------------------------------------------------------------------------

def read_jsonl(path: pathlib.Path) -> list:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def prompts_digest(items: list) -> str:
    """The dataset digest, rebuilt from the prompts on disk rather than read from the manifest."""
    running = hashlib.sha256()
    for item in items:
        running.update(item["id"].encode())
        running.update(item["prompt"].encode("utf-8"))
    return running.hexdigest()


def check(results: list, label: str, got, want) -> bool:
    ok = got == want
    results.append((ok, label, got, want))
    return ok


PROBES = pathlib.Path(__file__).resolve().parent / "probes"
VERDICTS = {"# MUST BE ACCEPTED": True, "# MUST BE REFUSED": False}


def run_probes(results: list) -> None:
    """Point the walker at files whose correct verdict is written on their first line.

    A check that has never been shown to fail is a check nobody has tested. Each probe declares,
    on line one, whether the walker must accept or refuse it, and the walker's verdict has to
    match. The accepted ones matter as much as the refused ones: a walker that refused everything
    would pass a suite of refusals and be useless.
    """
    files = sorted(PROBES.glob("*.py"))
    if len(files) < 8:
        check(results, "the probe directory holds enough probes to be meaningful",
              len(files), ">= 8")
        return
    for path in files:
        first = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
        if first not in VERDICTS:
            check(results, f"probe {path.name} declares its verdict on line one", first,
                  " or ".join(VERDICTS))
            continue
        expected = VERDICTS[first]
        try:
            assert_no_package_import(path)
            got = True
        except ImportLeak:
            got = False
        check(results, f"probe {path.name} is "
                       f"{'accepted' if expected else 'refused'}", got, expected)


def run(results: list) -> None:
    """Every recount. Records into `results`; returns early only when a prerequisite is absent,
    and records that absence as a failed check first, so a missing file can never be mistaken for
    a clean run."""
    graph = assert_no_package_import(pathlib.Path(__file__))
    print(f"import graph: {len(graph)} file(s) walked, none reach `{PACKAGE_UNDER_TEST}`")
    run_probes(results)

    items = read_jsonl(ROOT / "data" / "problems.jsonl")
    by_id = {item["id"]: item for item in items}
    check(results, "dataset holds 500 prompts", len(items), 500)

    answers_dir = ROOT / "results" / "answers"
    if not answers_dir.is_dir():
        check(results, "results/answers exists, so there is something to recount "
                       "(run `python3 -m exactly answers`)", False, True)
        return

    def graded(name: str):
        rows = read_jsonl(answers_dir / (name + ".jsonl"))
        if len(rows) != len(items):
            raise SystemExit(f"{name}.jsonl holds {len(rows)} answers for {len(items)} prompts")
        return [(by_id[row["id"]], row["response"]) for row in rows]

    reference = graded("reference")
    check(results, "reference answers are all compliant",
          sum(1 for item, text in reference if compliant(item, text)), 500)
    check(results, "off-by-one answers never satisfy the count",
          sum(1 for item, text in graded("off_by_one") if count_ok(item, text)), 0)
    filler = graded("filler")
    check(results, "filler hits every count", sum(1 for i, t in filler if count_ok(i, t)), 500)
    check(results, "filler carries no keyword",
          sum(1 for item, text in filler if keyword_present(text, item["keyword"])), 0)
    check(results, "filler with the keyword satisfies everything",
          sum(1 for i, t in graded("filler_keyword") if compliant(i, t)), 500)
    check(results, "the blank baseline satisfies nothing",
          sum(1 for i, t in graded("blank") if compliant(i, t)), 0)

    leaderboard = ROOT / "results" / "leaderboard.json"
    if not leaderboard.exists():
        check(results, "results/leaderboard.json exists to be checked against "
                       "(run `python3 -m exactly report`)", False, True)
        return
    board = json.loads(leaderboard.read_text(encoding="utf-8"))
    claimed = {entry["system"]: entry for entry in board["systems"]}
    manifest = json.loads((ROOT / "data" / "dataset.json").read_text(encoding="utf-8"))
    check(results, "the leaderboard scores the prompt set the dataset manifest describes",
          board["dataset"]["prompts_sha256"], manifest["prompts_sha256"])
    check(results, "the manifest digest is the digest of the prompts on disk",
          manifest["prompts_sha256"], prompts_digest(items))

    # The headline sensitivity number, recounted. `report.sensitivity_for` scores the affected
    # items under every dialect and reports the spread between best and worst; this walks the
    # same definition with the counters above and must land on the same figure.
    words_items = [(item, text) for item, text in reference if item["dimension"] == "words"]
    rates = {}
    for dialect in ("plain", "hyphen_split", "whitespace", "alpha_only"):
        ok = 0
        for item, text in words_items:
            observed = count_words_dialect(text.strip(), dialect)
            if item["mode"] == "exact":
                ok += observed == item["target"]
            elif item["mode"] == "at_most":
                ok += observed <= item["target"]
            else:
                ok += observed >= item["target"]
        rates[dialect] = round(ok / len(words_items), 4)
    recounted_spread = round((max(rates.values()) - min(rates.values())) * 100, 2)
    check(results, "the words rule sensitivity for the reference answers",
          recounted_spread, claimed["reference"]["sensitivity"]["words"]["spread_points"])
    print(f"  words dialect rates, recounted over {len(words_items)} items: {rates}")

    def tallies(rows):
        """Four independent totals, not one.

        A single `compliant` total can agree while two errors cancel: one answer wrongly passed on
        the count and another wrongly failed on the keyword sum to the same number. Comparing the
        count, the keyword and the uniqueness tallies separately makes that cancellation much
        harder, and it is what caught the one real disagreement in this project, where the
        checker's keyword matcher missed a word sitting between two em dashes.
        """
        return {
            "compliant": sum(1 for item, text in rows if compliant(item, text)),
            "count_ok": sum(1 for item, text in rows if count_ok(item, text)),
            "keyword_ok": sum(1 for item, text in rows
                              if keyword_present((text or "").strip(), item["keyword"])),
            "unique_ok": sum(1 for item, text in rows
                             if not (item["unique"]
                                     and has_duplicate_items((text or "").strip()))),
        }

    def compare(label, rows, overall):
        mine = tallies(rows)
        for field, got in sorted(mine.items()):
            check(results, f"leaderboard agrees with the recount of {field} for {label}",
                  got, overall[field])

    for name, entry in sorted(claimed.items()):
        if entry["kind"] != "baseline":
            continue
        compare(f"baseline {name}", graded(name), entry["strict"]["overall"])

    fixtures = sorted((ROOT / "fixtures" / "responses").glob("*.jsonl"))
    if not fixtures:
        check(results, "at least one recorded model fixture exists, or the model half of the "
                       "leaderboard is unchecked (record one with scripts/record.py)", 0, ">= 1")
        return
    for path in fixtures:
        rows = read_jsonl(path)
        answered = {row["id"]: row.get("response", "") for row in rows}
        entry = claimed.get(path.stem)
        if entry is None:
            check(results, f"{path.stem} appears on the leaderboard", False, True)
            continue
        compare(f"model {path.stem}",
                [(item, answered.get(item["id"], "")) for item in items],
                entry["strict"]["overall"])

def main() -> int:
    results = []
    run(results)
    failed = [row for row in results if not row[0]]
    for ok, label, got, want in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: got {got}, wanted {want}")
    print(f"{len(results) - len(failed)}/{len(results)} independent recounts agreed")
    if failed:
        print(f"INDEPENDENT CHECK FAILED: {len(failed)} disagreement(s)", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
