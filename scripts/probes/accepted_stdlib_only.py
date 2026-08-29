# MUST BE ACCEPTED
"""The ordinary case. Nothing here reaches into the package under test.

Every probe in this directory is READ by `scripts/check_independent.py` and parsed with `ast`.
None of them is ever executed, which is why the refused ones can import a package that would
blow up if it were imported for real.
"""

import json
import re


def count(text):
    return len(re.findall(r"\S+", json.dumps(text)))
