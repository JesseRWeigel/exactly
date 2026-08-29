# MUST BE REFUSED
"""The obvious leak: the checker would be grading the code with the code."""

from exactly import rules

assert rules.count_words("one two") == 2
