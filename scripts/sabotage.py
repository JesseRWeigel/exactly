#!/usr/bin/env python3
"""Break the counting rules on purpose and confirm something notices. Three gates, plus a control.

A verify command that passes on a broken implementation is the default failure mode, so the only
way to know this suite is worth anything is to break the code and watch it complain. A sabotage
counts here only if all three of these hold, in order:

  GATE 1, IT APPLIES.  The edit landed and the file changed. An anchor that appears more than once
  in its file is REJECTED rather than replaced, because an edit that lands in a copy nothing runs
  is a no-op with a confident write-up attached, and that mistake has been made repeatedly in this
  fleet. `python3 scripts/sabotage.py --anchors` checks every anchor without running anything.

  GATE 2, IT MOVES THE MEASUREMENT.  The fingerprint over the rules, the prompts and the grader
  has to change. For a GUARD, which is code that lies dormant when its input is correct, the
  requirement inverts: an auditor that finds nothing wrong with a correct document cannot change
  the output when you disable it, so a guard must leave the fingerprint UNCHANGED and must still
  be caught. A guard sabotage that does move the fingerprint was never a guard and is reported as
  a misclassification rather than quietly accepted.

  GATE 3, IT IS CAUGHT.  At least one named checker fails: the unit suite, the independent
  recount, the privacy scan, or the regeneration diff against the committed results and page.
  The README fingerprint check is deliberately NOT a catcher. It would fire for every sabotage
  that moves the fingerprint, which is all of them, and would tell us nothing about whether the
  rules are actually tested.

THE NULL CONTROL RUNS FIRST AND THE RUN IS VOID WITHOUT IT. The tree is copied, unchanged, into a
DIFFERENTLY NAMED directory, and its fingerprint has to match the baseline byte for byte. If it
does not, the measurement is a function of where the code lives rather than of the code, gate 2
passes for free for every sabotage, and every score in the report would be meaningless. On
2026-08-06 exactly that happened to a harness in this fleet and eleven sabotages scored as proven
were proving nothing.

Usage:
    python3 scripts/sabotage.py            run the null control and every sabotage
    python3 scripts/sabotage.py --anchors  check only that every anchor is present and unique
    python3 scripts/sabotage.py --only NAME
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (name, kind, file, anchor, replacement, one line saying what breaks)
# kind is "attack" for code that changes an answer, "guard" for code that is dormant until
# something is wrong and therefore cannot change a correct answer by being removed.
SABOTAGES = (
    ("words_off_by_one", "attack", "exactly/rules.py",
     "def count_words(text: str, dialect: str = \"plain\") -> int:\n    return len(words(text, dialect))",
     "def count_words(text: str, dialect: str = \"plain\") -> int:\n    return len(words(text, dialect)) + 1",
     "the word counter reports one more word than there is"),

    ("words_hyphen_always_splits", "attack", "exactly/rules.py",
     "    if dialect == \"hyphen_split\":\n        prepared = prepared.replace(\"-\", \" \")",
     "    if dialect in (\"hyphen_split\", \"plain\"):\n        prepared = prepared.replace(\"-\", \" \")",
     "the published word rule splits state-of-the-art into four words"),

    ("words_em_dash_joins", "attack", "exactly/rules.py",
     "SEPARATING_DASHES = \"\u2014\u2013\u2015\u2212\"",
     "SEPARATING_DASHES = \"\"",
     "the dashes that separate stop separating, so a pair joined by an em dash counts as one word"),

    ("words_symbol_counts", "attack", "exactly/rules.py",
     "def _alnum(token: str) -> bool:\n    return any(ch.isalnum() for ch in token)",
     "def _alnum(token: str) -> bool:\n    return True",
     "a bare dash or emoji counts as a word"),

    ("sentences_off_by_one", "attack", "exactly/rules.py",
     "def count_sentences(text: str, dialect: str = \"plain\") -> int:\n    return len(sentences(text, dialect))",
     "def count_sentences(text: str, dialect: str = \"plain\") -> int:\n    return max(0, len(sentences(text, dialect)) - 1)",
     "the sentence counter loses the last sentence"),

    ("sentences_split_on_abbreviations", "attack", "exactly/rules.py",
     "    return bool(word) and word.lower() in ABBREVIATIONS",
     "    return False",
     "Dr. Smith becomes two sentences"),

    ("sentences_split_on_decimals", "attack", "exactly/rules.py",
     "            if before.isdigit() and after.isdigit():\n                index += 1\n                continue",
     "            if False:\n                index += 1\n                continue",
     "3.5 hours becomes a sentence boundary"),

    ("sentences_split_on_list_markers", "attack", "exactly/rules.py",
     "            if _is_list_marker_stop(text, index):",
     "            if False and _is_list_marker_stop(text, index):",
     "every numbered list item opens a new sentence"),

    ("bullets_count_nested", "attack", "exactly/rules.py",
     "        if dialect != \"all_levels\" and width >= 2:\n            continue",
     "        if False:\n            continue",
     "a nested sub-bullet counts as a bullet of the list"),

    ("bullets_off_by_one", "attack", "exactly/rules.py",
     "def count_bullets(text: str, dialect: str = \"plain\") -> int:\n    return len(bullet_lines(text, dialect))",
     "def count_bullets(text: str, dialect: str = \"plain\") -> int:\n    return len(bullet_lines(text, dialect)) + 1",
     "the bullet counter reports one bullet too many"),

    ("chars_count_bytes", "attack", "exactly/rules.py",
     "    if dialect == \"nfc_codepoints\":\n        return len(unicodedata.normalize(\"NFC\", stripped))\n    return len(stripped)",
     "    if dialect == \"nfc_codepoints\":\n        return len(unicodedata.normalize(\"NFC\", stripped))\n    return len(stripped.encode(\"utf-8\"))",
     "the published character rule counts UTF-8 bytes instead of code points"),

    ("chars_do_not_strip", "attack", "exactly/rules.py",
     "    _check(\"chars\", dialect)\n    stripped = text.strip()",
     "    _check(\"chars\", dialect)\n    stripped = text",
     "leading and trailing whitespace counts toward a character target"),

    ("lines_count_blanks", "attack", "exactly/rules.py",
     "    return [line for line in found if count_words(line)]",
     "    return found",
     "blank lines count toward a line target"),

    ("paragraphs_split_on_newline", "attack", "exactly/rules.py",
     "    if dialect == \"single_newline\":\n        return [line.strip() for line in text.split(\"\\n\") if count_words(line)]",
     "    if dialect in (\"single_newline\", \"blank_line\"):\n        return [line.strip() for line in text.split(\"\\n\") if count_words(line)]",
     "every line becomes a paragraph under the published rule"),

    ("items_compared_exactly", "attack", "exactly/rules.py",
     "    cleaned = \"\".join(ch if (ch.isalnum() or ch.isspace()) else \" \" for ch in body)\n    return \" \".join(cleaned.split()).casefold()",
     "    return body.strip()",
     "Red apples. and red apples stop being the same item"),

    ("grader_accepts_off_by_one", "attack", "exactly/grade.py",
     "    if mode == \"exact\":\n        return observed == target",
     "    if mode == \"exact\":\n        return abs(observed - target) <= 1",
     "the grader accepts an answer one unit out from an exact target"),

    ("grader_ignores_the_keyword", "attack", "exactly/grade.py",
     "    return wanted in found",
     "    return True",
     "the required keyword is never checked"),

    ("grader_passes_the_empty_answer", "attack", "exactly/grade.py",
     "        \"compliant\": bool(text) and count_ok and keyword_ok and unique_ok,",
     "        \"compliant\": count_ok and keyword_ok and unique_ok,",
     "an empty response can be graded compliant"),

    ("grader_drops_missing_responses", "attack", "exactly/grade.py",
     "    rows = [grade(item, responses.get(item[\"id\"]), ruleset, lenient) for item in items]",
     "    rows = [grade(item, responses[item[\"id\"]], ruleset, lenient)\n            for item in items if item[\"id\"] in responses]",
     "a system that answered half the dataset reports the score of the half it liked"),

    ("errors_blur_the_near_miss", "attack", "exactly/grade.py",
     "        \"off_by_one\": sum(1 for value in misses if abs(value) == 1),",
     "        \"off_by_one\": sum(1 for value in misses if abs(value) <= 3),",
     "off by three is reported as off by one, so the near miss stops being a signal"),

    ("sensitivity_measured_on_everything", "attack", "exactly/report.py",
     "    return [item for item in items if item[\"dimension\"] == dimension]",
     "    return list(items)",
     "the rule sensitivity is divided across items the rule cannot touch, shrinking it"),

    ("manifest_ignores_the_prompts", "attack", "exactly/generate.py",
     "        digest.update(item[\"id\"].encode())\n        digest.update(item[\"prompt\"].encode(\"utf-8\"))",
     "        digest.update(item[\"id\"].encode())",
     "the dataset digest stops depending on the prompt text"),

    ("prompt_hides_the_rule", "attack", "exactly/generate.py",
     "        f\"{HEADINGS[dimension]}. Your answer is checked against this rule and no other:\\n\"\n        + rules.explain(dimension, unique),",
     "        f\"{HEADINGS[dimension]}.\",",
     "the model is graded on a counting rule it was never told"),

    # Guards. Each is dormant while its input is correct, so removing it cannot change a correct
    # answer, and the requirement inverts: fingerprint UNCHANGED, and a checker still fails.
    ("guard_import_walker_ignores_importlib", "guard", "scripts/check_independent.py",
     "            if isinstance(target, ast.Attribute) and target.attr == \"import_module\":\n                name = \"importlib.import_module\"",
     "            if False:\n                name = \"importlib.import_module\"",
     "the independence walker stops seeing importlib.import_module"),

    ("guard_import_walker_is_not_transitive", "guard", "scripts/check_independent.py",
     "            for candidate in (path.parent / (head + \".py\"), path.parent / head / \"__init__.py\"):\n                if candidate.exists():\n                    queue.append(candidate.resolve())",
     "            del head",
     "the independence walker stops following local imports, so a leak one hop away passes"),

    ("guard_privacy_scan_goes_blind_at_a_nul", "guard", "scripts/privacy_scan.py",
     "    text = blob.decode(\"utf-8\", errors=\"replace\")",
     "    if b\"\\x00\" in blob:\n        return []\n    text = blob.decode(\"utf-8\", errors=\"replace\")",
     "one NUL byte makes the privacy scan skip a whole file, as grep -I does"),

    ("guard_privacy_scan_forgets_the_aws_pattern", "guard", "scripts/privacy_scan.py",
     "    (\"aws access key id\", re.compile(_join(\"AK\", \"IA\") + r\"[0-9A-Z]{16}\")),",
     "",
     "the privacy scan stops looking for one of the credential shapes it advertises"),

    ("guard_fixture_staleness_unchecked", "guard", "exactly/recorded.py",
     "        if recorded_digest != prompt_digest(wanted[item_id]):\n            stale.append(f\"{item_id} was answered from a different prompt\")",
     "        del recorded_digest",
     "answers recorded from an older prompt set are scored against today's prompts"),
)

# The checkers gate 3 consults, each run inside the sabotaged copy. The README fingerprint check
# is not among them on purpose: it fires for anything that moves the fingerprint and so would
# make every attack look caught without saying anything about the tests.
CATCHERS = (
    ("unit", ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]),
    ("independent", ["python3", "scripts/check_independent.py"]),
    ("privacy", ["python3", "scripts/privacy_scan.py"]),
    ("regen", ["python3", "scripts/regen_diff.py"]),
)


def copy_tree(destination: pathlib.Path) -> pathlib.Path:
    """A full copy, `.git` included.

    The git directory is copied on purpose. `scripts/privacy_scan.py` enumerates the tree with
    `git ls-files`, so in a copy without it the scan would fail for want of a repository rather
    than for want of a clean tree. Gate 3 would then be satisfied for every single sabotage by a
    checker that never looked at the sabotage, which is the same class of mistake as gate 2
    passing for free.
    """
    shutil.copytree(ROOT, destination,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return destination


def fingerprint(tree: pathlib.Path) -> str:
    done = subprocess.run(["python3", "-m", "exactly", "fingerprint"], cwd=tree,
                          capture_output=True, text=True)
    if done.returncode != 0:
        return f"<the fingerprint could not be computed: {done.stderr.strip()[-160:]}>"
    return done.stdout.strip()


def apply_sabotage(tree: pathlib.Path, target: str, anchor: str, replacement: str):
    """Edit the copy. Returns (applied, why not) and REFUSES a non-unique anchor."""
    path = tree / target
    if not path.exists():
        return False, f"{target} does not exist"
    body = path.read_text(encoding="utf-8")
    hits = body.count(anchor)
    if hits == 0:
        return False, f"the anchor does not appear in {target}"
    if hits > 1:
        return False, (f"the anchor appears {hits} times in {target}, so the edit could land in "
                       f"a copy nothing runs; make it unique before trusting this sabotage")
    path.write_text(body.replace(anchor, replacement), encoding="utf-8")
    return path.read_text(encoding="utf-8") != body, ""


def catchers_that_fire(tree: pathlib.Path) -> list:
    fired = []
    for name, command in CATCHERS:
        done = subprocess.run(command, cwd=tree, capture_output=True, text=True)
        if done.returncode != 0:
            fired.append(name)
    return fired


def check_anchors() -> int:
    problems = []
    for name, _, target, anchor, _, _ in SABOTAGES:
        body = (ROOT / target).read_text(encoding="utf-8")
        hits = body.count(anchor)
        if hits != 1:
            problems.append(f"{name}: anchor appears {hits} times in {target}")
    for line in problems:
        print(f"  FAIL {line}")
    print(f"{len(SABOTAGES) - len(problems)}/{len(SABOTAGES)} anchors present exactly once")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchors", action="store_true",
                        help="check anchor presence and uniqueness, run nothing")
    parser.add_argument("--only", default=None, help="run one sabotage by name")
    args = parser.parse_args()

    if args.anchors:
        return check_anchors()

    with tempfile.TemporaryDirectory() as holding:
        holding = pathlib.Path(holding)
        baseline_tree = copy_tree(holding / "baseline")
        baseline = fingerprint(baseline_tree)
        if baseline.startswith("<"):
            print(f"ABORT: the baseline fingerprint failed: {baseline}", file=sys.stderr)
            return 2
        print(f"baseline fingerprint: {baseline}")

        # The null control. A DIFFERENT directory name on purpose: if anything hashed depended on
        # the working directory, this is where it shows up, and the whole run is void if it does.
        control_tree = copy_tree(holding / "a-differently-named-copy")
        control = fingerprint(control_tree)
        if control != baseline:
            print("ABORT: the null control did not reproduce the baseline fingerprint.\n"
                  f"  baseline {baseline}\n  control  {control}\n"
                  "  The measurement tracks where the code lives rather than what it does, so "
                  "gate 2 would pass for free for every sabotage and no score here would mean "
                  "anything.", file=sys.stderr)
            return 2
        print("null control: an unchanged copy in a differently named directory fingerprints "
              "identically")
        print()

        chosen = [row for row in SABOTAGES if args.only in (None, row[0])]
        if not chosen:
            print(f"no sabotage named {args.only!r}", file=sys.stderr)
            return 2

        proven, problems = 0, []
        for index, (name, kind, target, anchor, replacement, what) in enumerate(chosen):
            tree = copy_tree(holding / f"case-{index:02d}")
            applied, why = apply_sabotage(tree, target, anchor, replacement)
            if not applied:
                problems.append(f"{name}: GATE 1 failed, {why}")
                print(f"  gate1 FAIL {name}: {why}")
                continue
            moved = fingerprint(tree) != baseline
            wanted_move = kind == "attack"
            if moved != wanted_move:
                if kind == "guard":
                    problems.append(
                        f"{name}: classified as a guard but it MOVED the fingerprint, so it was "
                        f"never dormant. Rerun it as a plain attack.")
                else:
                    problems.append(
                        f"{name}: GATE 2 failed, the fingerprint did not move. Either the "
                        f"measurement is too narrow and should be widened, or the corpus never "
                        f"exercises this code and the sabotage is inert.")
                print(f"  gate2 FAIL {name}")
                continue
            fired = catchers_that_fire(tree)
            if not fired:
                problems.append(f"{name}: GATE 3 failed, nothing caught it. {what}")
                print(f"  gate3 FAIL {name}: nothing caught it")
                continue
            proven += 1
            moved_word = "moved" if moved else "unchanged (guard)"
            print(f"  proven {name} [{kind}] fingerprint {moved_word}, "
                  f"caught by {', '.join(fired)}")

        print()
        for line in problems:
            print(f"  {line}")
        print(f"{proven}/{len(chosen)} sabotages proven under all three gates")
        return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
