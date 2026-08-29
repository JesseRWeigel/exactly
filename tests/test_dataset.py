"""The dataset, the reference control, and the fixture loader's two refusals.

`ReferenceControl` is the load-bearing class. A grader that no answer can satisfy is a bug that
looks exactly like a hard benchmark, so the reference composer answers all 500 prompts and every
one of them has to be graded compliant. Without that, a leaderboard of zeroes would be
indistinguishable from a broken counter.
"""

import json
import pathlib
import tempfile
import unittest

from exactly import baselines, compose, generate, grade, recorded, report, rules

ROOT = pathlib.Path(__file__).resolve().parent.parent


class Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items, cls.meta = generate.load()

    def test_the_committed_file_holds_five_hundred_prompts(self):
        self.assertEqual(len(self.items), 500)
        self.assertEqual(self.meta["count"], 500)

    def test_the_committed_file_matches_what_the_generator_builds_today(self):
        rebuilt = generate.build()
        self.assertEqual([item["id"] for item in rebuilt], [item["id"] for item in self.items])
        self.assertEqual([item["prompt"] for item in rebuilt],
                         [item["prompt"] for item in self.items])

    def test_the_manifest_digest_matches_the_prompts(self):
        self.assertEqual(generate.manifest(self.items)["prompts_sha256"],
                         self.meta["prompts_sha256"])

    def test_every_id_is_unique(self):
        ids = [item["id"] for item in self.items]
        self.assertEqual(len(set(ids)), len(ids))

    def test_every_prompt_states_the_rule_it_is_graded_under(self):
        for item in self.items:
            rule_text = rules.explain(item["dimension"], item["unique"])
            self.assertIn(rule_text, item["prompt"],
                          f"{item['id']} does not carry its own counting rule")

    def test_every_prompt_names_its_target_and_its_keyword(self):
        for item in self.items:
            self.assertIn(str(item["target"]), item["prompt"])
            self.assertIn(item["keyword"], item["prompt"])

    def test_the_unique_family_prompts_say_no_two_may_be_the_same(self):
        for item in self.items:
            if item["unique"]:
                self.assertIn("no two of them may say the same thing", item["prompt"])

    def test_the_families_cover_exact_targets_and_both_bounds(self):
        modes = {item["mode"] for item in self.items}
        self.assertEqual(modes, {"exact", "at_most", "at_least"})

    def test_every_dimension_with_a_counter_appears_in_the_dataset(self):
        used = {item["dimension"] for item in self.items}
        self.assertEqual(used, set(rules.COUNTERS))

    def test_the_generator_is_deterministic_from_its_seed(self):
        self.assertEqual([item["prompt"] for item in generate.build()],
                         [item["prompt"] for item in generate.build()])

    def test_writing_the_dataset_does_not_change_the_committed_bytes(self):
        before = (generate.DATA / "problems.jsonl").read_bytes()
        generate.write()
        self.assertEqual((generate.DATA / "problems.jsonl").read_bytes(), before)


class ReferenceControl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items, _ = generate.load()

    def test_the_reference_answer_satisfies_every_one_of_the_five_hundred(self):
        scored = grade.score(self.items, baselines.responses("reference", self.items))
        failures = [row["id"] for row in scored["rows"] if not row["compliant"]]
        self.assertEqual(failures, [], f"{len(failures)} reference answers were graded wrong")
        self.assertEqual(scored["overall"]["rate"], 1.0)

    def test_the_off_by_one_baseline_never_satisfies_the_count(self):
        scored = grade.score(self.items, baselines.responses("off_by_one", self.items))
        self.assertEqual(scored["overall"]["count_ok"], 0)

    def test_the_blank_baseline_scores_nothing(self):
        scored = grade.score(self.items, baselines.responses("blank", self.items))
        self.assertEqual(scored["overall"]["compliant"], 0)

    def test_the_filler_baseline_hits_every_count_and_no_keyword(self):
        scored = grade.score(self.items, baselines.responses("filler", self.items))
        self.assertEqual(scored["overall"]["count_ok"], len(self.items))
        self.assertEqual(scored["overall"]["keyword_ok"], 0)
        self.assertEqual(scored["overall"]["compliant"], 0)

    def test_the_filler_with_the_keyword_is_the_ceiling_and_scores_full_marks(self):
        scored = grade.score(self.items, baselines.responses("filler_keyword", self.items))
        self.assertEqual(scored["overall"]["rate"], 1.0)

    def test_the_approximate_baseline_produces_a_spread_of_errors(self):
        scored = grade.score(self.items, baselines.responses("approximate", self.items))
        profile = scored["overall"]["errors"]
        self.assertGreater(profile["over"], 0)
        self.assertGreater(profile["under"], 0)
        self.assertLess(scored["overall"]["rate"], 0.5)

    def test_the_reference_carries_the_shapes_the_rules_decide_about(self):
        """If no reference answer contained an abbreviation or a nested bullet, the alternative
        dialects would agree with the published one and the sensitivity number would be a
        vacuous zero. This asserts the corpus is actually exercising the hard cases."""
        answers = baselines.responses("reference", self.items)
        joined = "\n".join(answers.values())
        for shape in ("Dr. ", "e.g. ", "3.5", "\n  - ", "\n1. "):
            self.assertIn(shape, joined, f"no reference answer contains {shape!r}")


class Composer(unittest.TestCase):
    def test_a_word_target_is_hit_exactly_across_the_whole_range(self):
        for target in range(1, 130):
            text = compose.words_answer(target, "yeast", f"w-{target}")
            self.assertEqual(rules.count_words(text), target)

    def test_a_character_target_is_hit_exactly_across_the_whole_range(self):
        for target in range(20, 320):
            text = compose.chars_answer(target, "yeast", f"c-{target}")
            self.assertEqual(rules.count_chars(text), target)

    def test_a_sentence_target_is_hit_exactly(self):
        for target in range(1, 25):
            text = compose.sentences_answer(target, "yeast", f"s-{target}")
            self.assertEqual(rules.count_sentences(text), target)

    def test_a_bullet_target_is_hit_exactly_despite_the_nested_sub_bullets(self):
        for target in range(1, 25):
            text = compose.bullets_answer(target, "yeast", f"b-{target}")
            self.assertEqual(rules.count_bullets(text), target)

    def test_unique_items_are_actually_unique(self):
        for target in range(1, 25):
            text = compose.unique_items_answer(target, "yeast", f"u-{target}")
            self.assertEqual(rules.count_bullets(text), target)
            self.assertEqual(rules.duplicate_items(text), [])

    def test_a_character_target_too_small_for_the_keyword_is_refused(self):
        with self.assertRaises(ValueError):
            compose.chars_answer(3, "condensation", "c-3")

    def test_a_word_target_below_one_is_refused(self):
        with self.assertRaises(ValueError):
            compose.words_answer(0, "yeast", "w-0")

    def test_an_answer_does_not_depend_on_how_many_came_before_it(self):
        first = compose.words_answer(30, "yeast", "same-id")
        for _ in range(5):
            compose.words_answer(30, "yeast", "other-id")
        self.assertEqual(compose.words_answer(30, "yeast", "same-id"), first)


class FixtureLoader(unittest.TestCase):
    def setUp(self):
        self.items = [{"id": "a-001", "prompt": "count to three", "target": 3,
                       "dimension": "words", "mode": "exact", "unique": False,
                       "keyword": "yeast", "family": "f"}]

    def _write(self, directory, rows):
        path = pathlib.Path(directory) / "toy.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_a_matching_fixture_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write(directory, [{"id": "a-001", "response": "yeast rises here",
                                     "prompt_sha256": recorded.prompt_digest("count to three")}])
            answers, notes = recorded.responses("toy", self.items, directory)
            self.assertEqual(answers["a-001"], "yeast rises here")
            self.assertEqual(notes["missing"], 0)

    def test_a_fixture_recorded_from_a_different_prompt_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write(directory, [{"id": "a-001", "response": "yeast rises here",
                                     "prompt_sha256": recorded.prompt_digest("a different one")}])
            with self.assertRaises(recorded.StaleFixture):
                recorded.responses("toy", self.items, directory)

    def test_a_mostly_truncated_fixture_is_refused_rather_than_scored(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write(directory, [{"id": "a-001", "response": "yeast", "truncated": True,
                                     "prompt_sha256": recorded.prompt_digest("count to three")}])
            with self.assertRaises(recorded.TruncatedFixture):
                recorded.responses("toy", self.items, directory)

    def test_an_absent_fixture_directory_lists_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(recorded.available(pathlib.Path(directory) / "nope"), [])


class Sensitivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items, _ = generate.load()

    def test_the_affected_subset_is_the_items_the_rule_can_touch(self):
        subset = report.affected(self.items, "words")
        self.assertTrue(subset)
        self.assertTrue(all(item["dimension"] == "words" for item in subset))
        self.assertLess(len(subset), len(self.items))

    def test_the_items_dimension_is_measured_on_the_unique_family(self):
        subset = report.affected(self.items, "items")
        self.assertTrue(subset)
        self.assertTrue(all(item["unique"] for item in subset))

    def test_the_reference_answers_are_sensitive_to_the_rule_choice(self):
        """The whole project rests on this being nonzero. If the reference answers scored the
        same under every dialect, the published rule would not be doing any work and the
        sensitivity section of the report would be honest but empty."""
        answers = baselines.responses("reference", self.items)
        found = report.sensitivity_for(self.items, answers)
        self.assertGreater(found["worst"]["spread_points"], 0)
        self.assertIsNotNone(found["worst"]["dimension"])

    def test_the_published_dialect_scores_full_marks_for_the_reference(self):
        answers = baselines.responses("reference", self.items)
        found = report.sensitivity_for(self.items, answers)
        for dimension, entry in found.items():
            if dimension == "worst":
                continue
            self.assertEqual(entry["published_rate"], 1.0, dimension)

    def test_a_dimension_entry_reports_which_dialect_was_best_and_worst(self):
        answers = baselines.responses("reference", self.items)
        entry = report.sensitivity_for(self.items, answers)["sentences"]
        self.assertIn(entry["lowest"], rules.DIALECTS["sentences"])
        self.assertIn(entry["highest"], rules.DIALECTS["sentences"])


if __name__ == "__main__":
    unittest.main()
