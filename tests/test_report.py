"""The report, the page and the fingerprint.

The page is built from a synthetic report rather than from the committed one, so these tests keep
working when the fixtures are re-recorded and the real numbers move. What is asserted is that the
page CONTAINS THE NUMBERS IT WAS GIVEN. A page check that only asserts the file exists passes on a
page with no numbers in it at all, which has happened in this fleet more than once.
"""

import json
import pathlib
import tempfile
import unittest

from exactly import baselines, fingerprint, generate, page, report, rules


def synthetic_board(name, kind, rate, spread):
    families = {"words_exact": {"n": 10, "compliant": 5, "rate": rate, "count_ok": 6,
                                "keyword_ok": 9, "unique_ok": 10, "empty": 0,
                                "errors": {"n": 10, "count_violations": 4, "off_by_one": 2,
                                           "off_by_one_share_of_misses": 0.5, "over": 3,
                                           "under": 1, "mean_error": 0.4, "median_error": 0,
                                           "mean_abs_error": 1.2,
                                           "median_abs_relative_error": 0.05,
                                           "histogram": {key: 0 for key in ("0", "+1")}}}}
    overall = dict(families["words_exact"])
    return {
        "system": name, "kind": kind, "fixture": {},
        "strict": {"overall": overall, "families": families},
        "lenient_rate": rate, "packaging_gap_points": 0.0, "responses_unwrapped": 0,
        "sensitivity": {"words": {"n": 10, "flag": "count_ok", "published": "plain",
                                  "published_rate": rate,
                                  "by_dialect": {"plain": rate, "hyphen_split": rate - 0.1},
                                  "spread_points": spread, "lowest": "hyphen_split",
                                  "highest": "plain"},
                        "worst": {"dimension": "words", "spread_points": spread,
                                  "from": "hyphen_split", "to": "plain"}},
    }


SYNTHETIC = {
    "dataset": {"count": 500, "seed": 20260829, "prompts_sha256": "abc123def456abc7",
                "families": {"words_exact": 10},
                "published_rules": dict(rules.PUBLISHED)},
    "systems": [synthetic_board("reference", "baseline", 1.0, 12.5),
                synthetic_board("filler_keyword", "baseline", 1.0, 0.0),
                synthetic_board("ignore", "baseline", 0.0, 0.0),
                synthetic_board("toy-model", "model", 0.42, 7.25)],
}
SYNTHETIC["headline"] = report.headline(SYNTHETIC["systems"])


class Headline(unittest.TestCase):
    def test_the_best_model_is_a_model_and_not_a_baseline(self):
        self.assertEqual(SYNTHETIC["headline"]["best_model"], "toy-model")
        self.assertEqual(SYNTHETIC["headline"]["best_model_rate"], 0.42)

    def test_the_filler_ceiling_is_quoted_separately(self):
        self.assertEqual(SYNTHETIC["headline"]["filler_keyword_rate"], 1.0)

    def test_the_largest_sensitivity_is_the_largest_one(self):
        self.assertEqual(SYNTHETIC["headline"]["largest_sensitivity"]["spread_points"], 12.5)
        self.assertEqual(SYNTHETIC["headline"]["largest_sensitivity"]["system"], "reference")


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = page.render(SYNTHETIC)

    def test_the_page_shows_the_numbers_it_was_given(self):
        for needle in ("42.0%", "7.2 pt", "12.5 pt", "toy-model", "abc123def456abc7", "500"):
            self.assertIn(needle, self.html, f"the page never mentions {needle!r}")

    def test_the_page_is_self_contained_and_has_no_script(self):
        for forbidden in ("<script", "http://", "cdn.", "src=\"http"):
            self.assertNotIn(forbidden, self.html)

    def test_wide_content_scrolls_inside_its_own_container(self):
        self.assertIn("overflow-x: auto", self.html)
        self.assertNotIn("overflow-x: hidden", self.html)

    def test_the_page_names_every_system_on_the_board(self):
        for board in SYNTHETIC["systems"]:
            self.assertIn(board["system"], self.html)

    def test_the_page_states_the_published_rule_for_every_dimension(self):
        for dimension, dialect in rules.PUBLISHED.items():
            self.assertIn(dimension, self.html)
            self.assertIn(dialect, self.html)

    def test_writing_the_page_reads_the_committed_results(self):
        with tempfile.TemporaryDirectory() as directory:
            results = pathlib.Path(directory) / "results"
            results.mkdir()
            (results / "leaderboard.json").write_text(json.dumps(SYNTHETIC), encoding="utf-8")
            docs = pathlib.Path(directory) / "docs"
            written = page.write(results, docs)
            self.assertIn("toy-model", written.read_text(encoding="utf-8"))


class TextBoard(unittest.TestCase):
    def test_the_text_board_is_ordered_by_compliance(self):
        text = report.as_text(SYNTHETIC)
        lines = [line for line in text.split("\n") if line and not line.startswith(("dataset",
                                                                                    "system"))]
        self.assertTrue(lines[0].startswith("reference"))
        self.assertTrue(lines[-1].startswith("ignore"))

    def test_the_text_board_quotes_the_dataset_digest(self):
        self.assertIn("abc123def456abc7", report.as_text(SYNTHETIC))


class Fingerprint(unittest.TestCase):
    def test_the_fingerprint_is_stable_across_two_calls(self):
        self.assertEqual(fingerprint.digest(), fingerprint.digest())

    def test_the_fingerprint_covers_every_probe(self):
        probes = fingerprint.payload()["probes"]
        self.assertEqual(len(probes), len(fingerprint.PROBES))
        self.assertGreaterEqual(len(probes), 40)

    def test_the_fingerprint_moves_when_a_counting_rule_moves(self):
        """A fingerprint that did not move when the rules moved would make every sabotage pass
        gate 2 for free, which is the failure this whole harness exists to avoid."""
        before = fingerprint.payload()
        after = json.loads(json.dumps(before))
        after["probes"]["title abbreviation"]["sentences"]["plain"] += 1
        self.assertNotEqual(fingerprint.digest(before), fingerprint.digest(after))

    def test_the_two_accent_probes_are_genuinely_different_text(self):
        by_label = dict(fingerprint.PROBES)
        self.assertNotEqual(by_label["combining accent"], by_label["precomposed accent"])

    def test_no_recorded_model_response_reaches_the_fingerprint(self):
        """Model output is not reproducible, so a fingerprint that included it would move for
        reasons having nothing to do with the code and gate 2 would be free."""
        self.assertNotIn("fixtures", json.dumps(fingerprint.payload()))
        self.assertEqual(set(fingerprint.payload()["baselines"]),
                         {"reference"} | set(baselines.NAMES))


class Evaluate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items, _ = generate.load()

    def test_a_baseline_evaluates_end_to_end(self):
        answers = baselines.responses("reference", self.items)
        board = report.evaluate(self.items, "reference", "baseline", answers, {})
        self.assertEqual(board["strict"]["overall"]["rate"], 1.0)
        self.assertEqual(board["kind"], "baseline")
        self.assertGreater(board["sensitivity"]["worst"]["spread_points"], 0)

    def test_the_packaging_gap_is_zero_for_answers_with_no_packaging(self):
        answers = baselines.responses("reference", self.items)
        board = report.evaluate(self.items, "reference", "baseline", answers, {})
        self.assertEqual(board["packaging_gap_points"], 0.0)

    def test_a_fenced_answer_shows_up_as_a_packaging_gap(self):
        answers = {item["id"]: "```\n" + text + "\n```"
                   for item, text in zip(self.items,
                                         baselines.responses("reference", self.items).values())}
        board = report.evaluate(self.items, "fenced", "baseline", answers, {})
        self.assertGreater(board["packaging_gap_points"], 0)
        self.assertGreater(board["responses_unwrapped"], 0)


if __name__ == "__main__":
    unittest.main()
