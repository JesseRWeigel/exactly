# MUST BE REFUSED
"""A helper that imports the package. Refused on its own account, and it is also what
`refused_transitive_import.py` imports, so the walker has to follow it to get that one right."""

from exactly import compose

assert compose.answer
