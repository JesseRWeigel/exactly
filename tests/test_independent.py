"""Hold the two implementations of the published rules against each other, case by case.

`scripts/check_independent.py` recounts the whole dataset a second way and `scripts/verify.sh`
runs it, but a whole-dataset total only says the two disagreed somewhere. These tests say where,
on the corpus of tricky texts the fingerprint already carries, so a divergence names the case
rather than a number.

Loading the checker here does not compromise its independence. What that check forbids is the
CHECKER importing the package under test, which is what would let the package's bugs into the
second opinion. A test importing both and comparing them is the comparison itself.

The regression this file exists for: the checker's keyword matcher split on whitespace and the
ASCII hyphen only, so `**horsehair**---is`, with markdown bold and em dashes around the required
word, cleaned down to `horsehairis` and the keyword went missing. Three real answers out of five
hundred were being called failures by the recount and compliant by the grader. The published rule
says an em dash separates the tokens on either side of it, and now both implementations do.
"""

import importlib.util
import pathlib
import unittest

from exactly import fingerprint, grade, rules

CHECKER = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check_independent.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_independent_under_test", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


independent = _load()

# Shapes real models produced, plus the ones the rules make decisions about.
CASES = (
    "The bread rose overnight. It smelled of yeast.",
    "The strands of **yeast**—is carefully attached to the stick.",
    "A yeast-based method, e.g. the old one, works. Dr. Smith agreed.",
    "1. First thing.\n2. Second thing about yeast.\n3. Third thing.",
    "- one\n  - nested\n- two about yeast",
    "It took 3.5 hours and 1,000 grams of yeast. Then it stopped.",
    "```\nyeast makes the bread rise\n```",
    "yeast \U0001f600 rises",
    "café with yeast",
    "one\n\ntwo\n   \nthree about yeast",
    "Really?! Yes, yeast.",
    "It trailed off… Then yeast resumed.",
    "",
    "   \n  ",
)


class Counters(unittest.TestCase):
    def test_the_two_word_counters_agree(self):
        for text in CASES:
            self.assertEqual(rules.count_words(text), independent.count_words(text), repr(text))

    def test_the_two_sentence_counters_agree(self):
        for text in CASES:
            self.assertEqual(rules.count_sentences(text), independent.count_sentences(text),
                             repr(text))

    def test_the_two_bullet_counters_agree(self):
        for text in CASES:
            self.assertEqual(rules.count_bullets(text), independent.count_bullets(text),
                             repr(text))

    def test_the_two_character_counters_agree(self):
        for text in CASES:
            self.assertEqual(rules.count_chars(text), independent.count_chars(text), repr(text))

    def test_the_two_line_counters_agree(self):
        for text in CASES:
            self.assertEqual(rules.count_lines(text), independent.count_lines(text), repr(text))

    def test_the_two_paragraph_counters_agree(self):
        for text in CASES:
            self.assertEqual(rules.count_paragraphs(text), independent.count_paragraphs(text),
                             repr(text))

    def test_they_agree_on_every_probe_in_the_fingerprint_corpus(self):
        for label, text in fingerprint.PROBES:
            for name, mine in (("words", rules.count_words), ("sentences", rules.count_sentences),
                               ("bullets", rules.count_bullets), ("chars", rules.count_chars),
                               ("lines", rules.count_lines),
                               ("paragraphs", rules.count_paragraphs)):
                theirs = independent.COUNTERS[name]
                self.assertEqual(mine(text), theirs(text), f"{name} on probe {label!r}")


class Keyword(unittest.TestCase):
    def test_the_two_keyword_matchers_agree(self):
        for text in CASES:
            self.assertEqual(grade.keyword_present(text, "yeast"),
                             independent.keyword_present(text, "yeast"), repr(text))

    def test_a_bold_keyword_between_em_dashes_is_found_by_both(self):
        text = "the tensioned strands of **yeast**—is carefully attached"
        self.assertTrue(grade.keyword_present(text, "yeast"))
        self.assertTrue(independent.keyword_present(text, "yeast"))

    def test_a_keyword_glued_to_the_next_word_is_found_by_neither(self):
        text = "the tensioned strands of yeastis carefully attached"
        self.assertFalse(grade.keyword_present(text, "yeast"))
        self.assertFalse(independent.keyword_present(text, "yeast"))


class CountVerdict(unittest.TestCase):
    """The count verdict is about the count alone, in both implementations.

    Folding emptiness into it looks harmless and is not: under an upper bound zero of anything
    satisfies the count, and the `blank` baseline satisfying the count on 40 of the 500 items is
    how the leaderboard shows that `no more than 4 sentences` is satisfiable by silence. The
    checker's first version returned False for an empty answer and disagreed on exactly those 40.
    """

    def _item(self, mode, target=4):
        return {"id": "t-1", "family": "f", "dimension": "sentences", "mode": mode,
                "target": target, "unique": False, "keyword": "yeast"}

    def test_an_empty_answer_satisfies_an_upper_bound_in_both(self):
        item = self._item("at_most")
        self.assertTrue(grade.grade(item, "")["count_ok"])
        self.assertTrue(independent.count_ok(item, ""))

    def test_an_empty_answer_is_still_not_compliant_in_both(self):
        item = self._item("at_most")
        self.assertFalse(grade.grade(item, "")["compliant"])
        self.assertFalse(independent.compliant(item, ""))

    def test_an_empty_answer_fails_an_exact_target_in_both(self):
        item = self._item("exact")
        self.assertFalse(grade.grade(item, "")["count_ok"])
        self.assertFalse(independent.count_ok(item, ""))


class Duplicates(unittest.TestCase):
    def test_the_two_duplicate_detectors_agree(self):
        cases = ("- Red apples.\n- red apples\n- red cars",
                 "- one\n- two\n- three",
                 "- yeast is warm\n- Yeast is warm.\n- yeast is cold")
        for text in cases:
            self.assertEqual(bool(rules.duplicate_items(text)),
                             independent.has_duplicate_items(text), repr(text))


class Independence(unittest.TestCase):
    def test_the_checker_does_not_import_the_package_under_test(self):
        graph = independent.assert_no_package_import(CHECKER)
        self.assertGreaterEqual(len(graph), 1)

    def test_every_probe_gets_the_verdict_it_declares(self):
        probes = sorted((CHECKER.parent / "probes").glob("*.py"))
        self.assertGreaterEqual(len(probes), 8)
        for path in probes:
            first = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
            self.assertIn(first, independent.VERDICTS, f"{path.name} declares no verdict")
            try:
                independent.assert_no_package_import(path)
                got = True
            except independent.ImportLeak:
                got = False
            self.assertEqual(got, independent.VERDICTS[first], path.name)


if __name__ == "__main__":
    unittest.main()
