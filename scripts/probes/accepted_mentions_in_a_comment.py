# MUST BE ACCEPTED
"""A file that TALKS about the package without importing it.

This is the probe that a grep-based independence check fails. The string below is exactly what a
grep for the package name would match, and the correct verdict is still accept, because reading
the source with `ast` shows there is no import here at all.
"""

import json

DOCUMENTATION = "the published rules live in `from exactly import rules`, which we do not import"

# from exactly import rules
# import exactly.grade

assert "exactly" in DOCUMENTATION
assert json
