"""Grading, unwrapping and the error profile.

The load-bearing assertion in this file is `test_off_by_one_is_not_compliant`. A grader that
accepts an answer one unit out is not counting, and every number this project publishes rests on
it being false.
"""

import unittest

from exactly import baselines, grade, rules


def item(**overrides):
    made = {"id": "t-001", "family": "words_exact", "dimension": "words", "mode": "exact",
            "target": 5, "unique": False, "keyword": "yeast", "checks": ["count", "keyword"]}
    made.update(overrides)
    return made


class Satisfies(unittest.TestCase):
    def test_exact_needs_equality(self):
        self.assertTrue(grade.satisfies("exact", 5, 5))
        self.assertFalse(grade.satisfies("exact", 4, 5))
        self.assertFalse(grade.satisfies("exact", 6, 5))

    def test_at_most_is_an_upper_bound(self):
        self.assertTrue(grade.satisfies("at_most", 1, 5))
        self.assertTrue(grade.satisfies("at_most", 5, 5))
        self.assertFalse(grade.satisfies("at_most", 6, 5))

    def test_at_least_is_a_lower_bound(self):
        self.assertTrue(grade.satisfies("at_least", 50, 5))
        self.assertFalse(grade.satisfies("at_least", 4, 5))

    def test_an_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            grade.satisfies("about", 5, 5)


class Grading(unittest.TestCase):
    def test_a_correct_answer_is_compliant(self):
        row = grade.grade(item(), "yeast makes the bread rise")
        self.assertTrue(row["compliant"])
        self.assertEqual(row["observed"], 5)
        self.assertEqual(row["error"], 0)

    def test_off_by_one_is_not_compliant(self):
        row = grade.grade(item(), "yeast makes the bread rise slowly")
        self.assertFalse(row["compliant"])
        self.assertEqual(row["error"], 1)
        self.assertIn("6 words against a target of 5", row["reasons"])

    def test_a_missing_keyword_fails_even_with_a_perfect_count(self):
        row = grade.grade(item(), "sugar makes the bread rise")
        self.assertTrue(row["count_ok"])
        self.assertFalse(row["keyword_ok"])
        self.assertFalse(row["compliant"])

    def test_an_empty_response_is_a_failure_and_not_a_vacuous_pass(self):
        row = grade.grade(item(), "")
        self.assertTrue(row["empty"])
        self.assertFalse(row["compliant"])
        self.assertIn("the response is empty", row["reasons"])

    def test_a_missing_response_is_graded_as_empty_rather_than_dropped(self):
        row = grade.grade(item(), None)
        self.assertTrue(row["empty"])
        self.assertFalse(row["compliant"])

    def test_the_keyword_is_matched_whole_word_and_case_insensitively(self):
        self.assertTrue(grade.keyword_present("The Yeast rose", "yeast"))
        self.assertFalse(grade.keyword_present("yeasty bread here", "yeast"))

    def test_a_hyphenated_compound_contains_its_parts_for_the_keyword(self):
        self.assertTrue(grade.keyword_present("a yeast-based method", "yeast"))

    def test_the_keyword_survives_adjacent_punctuation(self):
        self.assertTrue(grade.keyword_present("what about (yeast), then", "yeast"))

    def test_duplicate_items_fail_the_unique_family(self):
        text = "- yeast is warm\n- Yeast is warm.\n- yeast is cold"
        row = grade.grade(item(dimension="bullets", target=3, unique=True,
                               family="unique_items"), text)
        self.assertTrue(row["count_ok"])
        self.assertFalse(row["unique_ok"])
        self.assertFalse(row["compliant"])

    def test_distinct_items_pass_the_unique_family(self):
        text = "- yeast is warm\n- yeast is cold\n- yeast is old"
        row = grade.grade(item(dimension="bullets", target=3, unique=True,
                               family="unique_items"), text)
        self.assertTrue(row["compliant"])

    def test_a_ruleset_override_can_change_the_verdict(self):
        text = "yeast makes state-of-the-art bread rise"
        self.assertTrue(grade.grade(item(), text)["count_ok"])
        loose = rules.ruleset_from({"words": "hyphen_split"})
        self.assertFalse(grade.grade(item(), text, loose)["count_ok"])


class Unwrapping(unittest.TestCase):
    def test_a_code_fence_is_stripped_only_in_lenient_mode(self):
        # Checked on a CHARACTER target, because a fence is invisible to the word rule: a run of
        # backticks holds no letter or digit, so it is not a word either way. Packaging changes
        # the verdict for the dimensions that can see it, which is the point of the two readings.
        text = "```\nyeast makes the bread rise\n```"
        chars = item(dimension="chars", target=len("yeast makes the bread rise"))
        self.assertFalse(grade.grade(chars, text)["count_ok"])
        self.assertTrue(grade.grade(chars, text, lenient=True)["count_ok"])

    def test_a_fence_does_not_change_a_word_count_either_way(self):
        text = "```\nyeast makes the bread rise\n```"
        self.assertTrue(grade.grade(item(), text)["count_ok"])

    def test_a_short_preamble_line_is_stripped_in_lenient_mode(self):
        text = "Here is the answer:\nyeast makes the bread rise"
        self.assertFalse(grade.grade(item(), text)["count_ok"])
        lenient = grade.grade(item(), text, lenient=True)
        self.assertTrue(lenient["count_ok"])
        self.assertIn("preamble line", lenient["unwrapped"])

    def test_a_self_reported_count_line_is_stripped_in_lenient_mode(self):
        text = "yeast makes the bread rise\n(5 words)"
        self.assertTrue(grade.grade(item(), text, lenient=True)["count_ok"])

    def test_strict_mode_never_unwraps(self):
        text = "```\nyeast makes the bread rise\n```"
        self.assertEqual(grade.grade(item(), text)["unwrapped"], [])

    def test_a_long_first_line_ending_in_a_colon_is_left_alone(self):
        # The preamble rule strips a line of at most 14 words. That threshold is arbitrary and it
        # is meant to be: a long sentence that happens to end in a colon is part of the answer,
        # and a lenient reading that ate it would be inventing compliance rather than measuring
        # packaging. Sixteen words here, comfortably the far side of the line.
        body = ("the following paragraph below is my complete and fully considered answer to the "
                "question that you asked me:")
        self.assertGreater(rules.count_words(body), 14)
        text = body + "\nyeast makes the bread rise"
        self.assertFalse(grade.grade(item(), text, lenient=True)["count_ok"])


class ErrorProfile(unittest.TestCase):
    def test_the_buckets_partition_the_number_line(self):
        for value in range(-25, 26):
            self.assertIn(grade.bucket(value), grade.BUCKETS)

    def test_off_by_one_is_separated_from_off_by_forty(self):
        rows = [{"error": 1, "count_ok": False, "target": 7},
                {"error": 40, "count_ok": False, "target": 7}]
        profile = grade.error_profile(rows)
        self.assertEqual(profile["off_by_one"], 1)
        self.assertEqual(profile["off_by_one_share_of_misses"], 0.5)
        self.assertEqual(profile["over"], 2)
        self.assertEqual(profile["under"], 0)

    def test_direction_is_recorded_separately_from_magnitude(self):
        rows = [{"error": -3, "count_ok": False, "target": 10},
                {"error": 3, "count_ok": False, "target": 10}]
        profile = grade.error_profile(rows)
        self.assertEqual(profile["mean_error"], 0.0)
        self.assertEqual(profile["mean_abs_error"], 3.0)
        self.assertEqual((profile["over"], profile["under"]), (1, 1))

    def test_an_all_correct_group_has_no_off_by_one_share(self):
        profile = grade.error_profile([{"error": 0, "count_ok": True, "target": 5}])
        self.assertIsNone(profile["off_by_one_share_of_misses"])


class Scoring(unittest.TestCase):
    def setUp(self):
        self.items = [item(id="a-001", target=3), item(id="a-002", target=4)]

    def test_a_response_missing_from_the_mapping_counts_against_the_score(self):
        scored = grade.score(self.items, {"a-001": "yeast rises here"})
        self.assertEqual(scored["overall"]["n"], 2)
        self.assertEqual(scored["overall"]["compliant"], 1)
        self.assertEqual(scored["overall"]["rate"], 0.5)

    def test_families_are_kept_apart(self):
        mixed = [item(id="a-001", target=3, family="one"),
                 item(id="b-001", target=3, family="two")]
        scored = grade.score(mixed, {"a-001": "yeast rises here"})
        self.assertEqual(scored["families"]["one"]["rate"], 1.0)
        self.assertEqual(scored["families"]["two"]["rate"], 0.0)


class Baselines(unittest.TestCase):
    def test_the_off_by_one_baseline_breaks_the_bound_in_the_right_direction(self):
        self.assertEqual(baselines._wrong_target(item(mode="at_most", target=5)), 6)
        self.assertEqual(baselines._wrong_target(item(mode="at_least", target=5)), 4)
        self.assertEqual(baselines._wrong_target(item(mode="exact", target=5)), 6)

    def test_the_jitter_is_never_zero_and_is_stable_per_item(self):
        for target in (2, 7, 40, 300):
            for index in range(20):
                step = baselines._jitter(f"x-{index:03d}", target)
                self.assertNotEqual(step, 0)
        self.assertEqual(baselines._jitter("x-001", 7), baselines._jitter("x-001", 7))

    def test_the_filler_answer_hits_the_count_and_misses_the_point(self):
        text = baselines.answer("filler", item(target=6))
        self.assertEqual(rules.count_words(text), 6)
        self.assertFalse(grade.keyword_present(text, "yeast"))

    def test_the_filler_with_the_keyword_satisfies_every_check(self):
        row = grade.grade(item(target=6), baselines.answer("filler_keyword", item(target=6)))
        self.assertTrue(row["compliant"])

    def test_an_unknown_baseline_raises(self):
        with self.assertRaises(ValueError):
            baselines.answer("psychic", item())


if __name__ == "__main__":
    unittest.main()
