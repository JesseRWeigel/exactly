# MUST BE ACCEPTED
"""A stdlib import bound to a name that happens to be the package name.

What matters is the module that gets loaded, which is `json`, not the local name it is bound to.
A checker looking at bindings rather than at module names would refuse this and be wrong.
"""

import json as exactly

assert exactly.dumps
