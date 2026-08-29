# MUST BE ACCEPTED
"""A different package whose name merely starts with the same letters.

`exactly_other` is not `exactly` and is not a submodule of it. A check that matched on a bare
prefix would refuse this file and would be wrong, so the rule is an exact name or a dotted
submodule of it.
"""

import exactly_other
import exactlyish.helpers

assert exactly_other and exactlyish
