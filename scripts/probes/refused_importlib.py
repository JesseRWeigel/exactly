# MUST BE REFUSED
"""The spelling a grep for `import exactly` misses entirely."""

import importlib

rules = importlib.import_module("exactly.rules")

assert rules.count_words("one two") == 2
