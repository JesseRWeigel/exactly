"""exactly: does a model do what it is counted for.

The package is deliberately split so that nothing which produces a number can also produce a
response. `rules` counts, `compose` writes text that satisfies a count, `generate` builds the
prompt set, `grade` judges one response, `baselines` supplies systems that answer without a model,
`recorded` reads answers a real model already gave, and `report` aggregates. Only
`scripts/record.py`, which is outside the package, opens a socket.
"""

__all__ = ["baselines", "compose", "corpus", "fingerprint", "generate", "grade",
           "page", "recorded", "report", "rules"]
