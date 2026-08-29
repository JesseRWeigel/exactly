# MUST BE REFUSED
"""Imports nothing from the package DIRECTLY, and still fails.

The leak is one hop away, through a local module. An independence check that only looked at its
own first file would clear this, and the code it was meant to be independent of would be running
inside it. Following local imports is the whole reason the walk is a graph.
"""

import json

import refused_reaches_in_helper

assert json and refused_reaches_in_helper
