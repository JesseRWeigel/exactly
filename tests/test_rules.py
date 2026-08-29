"""Every counting decision this project makes, written down as an assertion.

These are not smoke tests. Each one names a case where a defensible counter would disagree with
this one, so the file doubles as the specification the README points at. If a number here changes,
the benchmark changed, and the change should be visible in a diff rather than absorbed silently.
"""

import unittest

from exactly import rules


class Words(unittest.TestCase):
    def test_hyphenated_compound_is_one_word_under_plain(self):
        self.assertEqual(rules.count_words("state-of-the-art design"), 2)

    def test_hyphenated_compound_splits_under_hyphen_split(self):
        self.assertEqual(rules.count_words("state-of-the-art design", "hyphen_split"), 5)

    def test_contraction_is_one_word(self):
        self.assertEqual(rules.count_words("don't stop"), 2)

    def test_number_is_a_word_under_plain_and_not_under_alpha_only(self):
        self.assertEqual(rules.count_words("about 3.14 exactly"), 3)
        self.assertEqual(rules.count_words("about 3.14 exactly", "alpha_only"), 2)

    def test_url_is_one_word(self):
        self.assertEqual(rules.count_words("see https://example.com/a/b now"), 3)

    def test_lone_symbol_is_not_a_word_but_counts_under_whitespace(self):
        self.assertEqual(rules.count_words("a + b"), 2)
        self.assertEqual(rules.count_words("a + b", "whitespace"), 3)

    def test_emoji_is_not_a_word_under_plain(self):
        self.assertEqual(rules.count_words("good \U0001f600 morning"), 2)
        self.assertEqual(rules.count_words("good \U0001f600 morning", "whitespace"), 3)

    def test_em_dash_separates_and_hyphen_joins(self):
        self.assertEqual(rules.count_words("one—two"), 2)
        self.assertEqual(rules.count_words("one-two"), 1)

    def test_en_dash_separates(self):
        self.assertEqual(rules.count_words("1999–2003"), 2)

    def test_thousands_separator_stays_one_word(self):
        self.assertEqual(rules.count_words("about 1,000 items"), 3)

    def test_unknown_dialect_raises_rather_than_defaulting(self):
        with self.assertRaises(rules.UnknownDialect):
            rules.count_words("anything", "sensible")


class Sentences(unittest.TestCase):
    def test_title_abbreviation_does_not_split(self):
        self.assertEqual(rules.count_sentences("Dr. Smith arrived. He waited."), 2)

    def test_naive_dialect_does_split_on_the_abbreviation(self):
        self.assertEqual(rules.count_sentences("Dr. Smith arrived. He waited.", "naive"), 3)

    def test_eg_does_not_split(self):
        self.assertEqual(rules.count_sentences("Some books, e.g. the old ones, are good."), 1)

    def test_decimal_point_does_not_split(self):
        self.assertEqual(rules.count_sentences("It took 3.5 hours. Then it stopped."), 2)

    def test_numbered_list_marker_does_not_open_a_sentence(self):
        text = "1. First thing.\n2. Second thing.\n3. Third thing."
        self.assertEqual(rules.count_sentences(text), 3)

    def test_trailing_fragment_counts_under_plain_and_not_under_require_terminator(self):
        text = "One sentence here. A fragment with no stop"
        self.assertEqual(rules.count_sentences(text), 2)
        self.assertEqual(rules.count_sentences(text, "require_terminator"), 1)

    def test_closing_quote_belongs_to_the_sentence_it_closes(self):
        self.assertEqual(rules.count_sentences('He said "stop now." Then he left.'), 2)

    def test_ellipsis_ends_a_sentence(self):
        self.assertEqual(rules.count_sentences("It trailed off… Then it resumed."), 2)

    def test_run_of_terminators_is_one_boundary(self):
        self.assertEqual(rules.count_sentences("Really?! Yes."), 2)

    def test_lowercase_after_a_stop_does_not_split(self):
        self.assertEqual(rules.count_sentences("Ordered from acme. inc and shipped."), 1)

    def test_newline_breaks_dialect_splits_on_a_line_break(self):
        text = "First line\nSecond line"
        self.assertEqual(rules.count_sentences(text), 1)
        self.assertEqual(rules.count_sentences(text, "newline_breaks"), 2)

    def test_empty_text_has_no_sentences(self):
        self.assertEqual(rules.count_sentences(""), 0)
        self.assertEqual(rules.count_sentences("   \n  "), 0)


class Bullets(unittest.TestCase):
    def test_nested_sub_bullet_is_not_counted_under_plain(self):
        text = "- one\n  - nested\n- two"
        self.assertEqual(rules.count_bullets(text), 2)
        self.assertEqual(rules.count_bullets(text, "all_levels"), 3)

    def test_numbered_list_is_bullets_under_plain_and_not_under_dash_only(self):
        text = "1. one\n2. two\n3. three"
        self.assertEqual(rules.count_bullets(text), 3)
        self.assertEqual(rules.count_bullets(text, "dash_only"), 0)

    def test_marker_needs_a_space_and_a_body(self):
        self.assertEqual(rules.count_bullets("-nospace\n- yes"), 1)
        self.assertEqual(rules.count_bullets("- \n- yes"), 1)

    def test_tab_indent_counts_as_four_columns(self):
        self.assertEqual(rules.count_bullets("\t- nested"), 0)
        self.assertEqual(rules.count_bullets("\t- nested", "all_levels"), 1)

    def test_one_space_indent_still_counts_as_top_level(self):
        self.assertEqual(rules.count_bullets(" - one\n - two"), 2)

    def test_paren_and_letter_markers_count(self):
        self.assertEqual(rules.count_bullets("(1) one\nb) two\n• three"), 3)

    def test_a_dash_inside_a_line_is_not_a_bullet(self):
        self.assertEqual(rules.count_bullets("a line - with a dash"), 0)


class Items(unittest.TestCase):
    def test_case_and_punctuation_do_not_make_a_new_item(self):
        text = "- Red apples.\n- red apples"
        self.assertEqual(rules.duplicate_items(text), ["red apples"])

    def test_exact_dialect_calls_them_different(self):
        text = "- Red apples.\n- red apples"
        self.assertEqual(rules.duplicate_items(text, "plain", "exact"), [])

    def test_first_word_dialect_is_much_stricter(self):
        text = "- red apples\n- red cars"
        self.assertEqual(rules.duplicate_items(text), [])
        self.assertEqual(rules.duplicate_items(text, "plain", "first_word"), ["red"])

    def test_distinct_items_have_no_duplicates(self):
        self.assertEqual(rules.duplicate_items("- one\n- two\n- three"), [])


class CharsLinesParagraphs(unittest.TestCase):
    def test_codepoints_count_spaces_and_punctuation(self):
        self.assertEqual(rules.count_chars("ab cd."), 6)

    def test_surrounding_whitespace_is_stripped_first(self):
        self.assertEqual(rules.count_chars("  ab  "), 2)

    def test_no_whitespace_dialect_drops_the_space(self):
        self.assertEqual(rules.count_chars("ab cd.", "no_whitespace"), 5)

    def test_utf8_bytes_differ_from_codepoints_for_an_accent(self):
        # Written as escapes rather than as literal accented text, because two visually identical
        # literals in one file that differ only in normalisation is a trap for the next reader.
        precomposed = "caf\u00e9"
        self.assertEqual(rules.count_chars(precomposed), 4)
        self.assertEqual(rules.count_chars(precomposed, "utf8_bytes"), 5)

    def test_nfc_normalisation_joins_a_combining_accent(self):
        decomposed = "cafe\u0301"
        self.assertEqual(rules.count_chars(decomposed), 5)
        self.assertEqual(rules.count_chars(decomposed, "nfc_codepoints"), 4)

    def test_blank_lines_do_not_count_under_nonblank(self):
        text = "one\n\ntwo\n   \nthree"
        self.assertEqual(rules.count_lines(text), 3)
        self.assertEqual(rules.count_lines(text, "all_lines"), 5)
        # `stripped_all` and `nonblank` agree here: a whitespace-only line has no non-whitespace
        # in it either. They part company on a line of punctuation, which the next test covers.
        self.assertEqual(rules.count_lines(text, "stripped_all"), 3)

    def test_a_line_of_punctuation_only_is_not_a_line_under_nonblank(self):
        self.assertEqual(rules.count_lines("one\n---\ntwo"), 2)
        self.assertEqual(rules.count_lines("one\n---\ntwo", "stripped_all"), 3)

    def test_paragraphs_split_on_blank_lines_not_single_newlines(self):
        text = "one\nstill one\n\ntwo"
        self.assertEqual(rules.count_paragraphs(text), 2)
        self.assertEqual(rules.count_paragraphs(text, "single_newline"), 3)

    def test_indent_or_blank_opens_a_paragraph_on_an_indented_line(self):
        text = "one\n    indented\n\ntwo"
        self.assertEqual(rules.count_paragraphs(text), 2)
        self.assertEqual(rules.count_paragraphs(text, "indent_or_blank"), 3)

    def test_several_blank_lines_are_one_separator(self):
        self.assertEqual(rules.count_paragraphs("one\n\n\n\ntwo"), 2)


class RuleSets(unittest.TestCase):
    def test_count_dispatches_to_the_published_dialect(self):
        self.assertEqual(rules.count("words", "state-of-the-art"), 1)

    def test_a_ruleset_override_changes_the_answer(self):
        ruleset = rules.ruleset_from({"words": "hyphen_split"})
        self.assertEqual(rules.count("words", "state-of-the-art", ruleset), 4)

    def test_an_override_leaves_the_other_dimensions_alone(self):
        ruleset = rules.ruleset_from({"words": "hyphen_split"})
        self.assertEqual(ruleset["sentences"], rules.PUBLISHED["sentences"])

    def test_a_bad_dimension_raises(self):
        with self.assertRaises(rules.UnknownDialect):
            rules.ruleset_from({"paragraph": "blank_line"})

    def test_every_published_dialect_is_a_real_dialect(self):
        for dimension, dialect in rules.PUBLISHED.items():
            self.assertIn(dialect, rules.DIALECTS[dimension])

    def test_every_dimension_with_a_counter_has_a_published_rule(self):
        for dimension in rules.COUNTERS:
            self.assertIn(dimension, rules.PUBLISHED)

    def test_every_explained_dimension_has_dialects_and_the_reverse(self):
        self.assertEqual(set(rules.EXPLANATIONS), set(rules.DIALECTS))


class Explanations(unittest.TestCase):
    def test_the_explanation_states_the_hyphen_decision(self):
        self.assertIn("state-of-the-art", rules.explain("words"))

    def test_the_unique_flag_appends_the_item_rule(self):
        self.assertNotIn("same item", rules.explain("bullets"))
        self.assertIn("same item", rules.explain("bullets", unique=True))

    def test_every_explanation_is_a_bulleted_block(self):
        for dimension in rules.EXPLANATIONS:
            for line in rules.explain(dimension).split("\n"):
                self.assertTrue(line.startswith("- "), f"{dimension}: {line!r}")


if __name__ == "__main__":
    unittest.main()
