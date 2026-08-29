# MUST BE REFUSED
"""An import whose module name is not knowable by reading the source.

Refused on the grounds that it CANNOT BE CLEARED, which is the honest verdict. A checker that
shrugged at a computed name would be trivially defeated by one line of string concatenation, and
"could not tell" must not report the same result as "checked and it was fine".
"""

import importlib

WANTED = "exact" + "ly.rules"

rules = importlib.import_module(WANTED)

assert rules
