"""The command line. Everything here is offline and deterministic; nothing opens a socket.

    python3 -m exactly build       regenerate data/problems.jsonl and data/dataset.json
    python3 -m exactly rules       print the published counting rules, as the prompts state them
    python3 -m exactly count       count one text from stdin, under every dialect
    python3 -m exactly answers     rewrite results/answers/<baseline>.jsonl from the composers
    python3 -m exactly report      rebuild results/leaderboard.json from the committed fixtures
    python3 -m exactly board       print the leaderboard from results/leaderboard.json
    python3 -m exactly page        rebuild docs/index.html from results/leaderboard.json
    python3 -m exactly fingerprint one sha256 over the rules, the prompts and the grader
    python3 -m exactly payload     the data that fingerprint hashes, so two runs can be diffed
"""

from __future__ import annotations

import json
import sys

from . import baselines, fingerprint, generate, page, report, rules


def _build() -> int:
    items, meta = generate.write()
    print(f"wrote {len(items)} prompts, sha256 {meta['prompts_sha256'][:16]}")
    return 0


def _rules() -> int:
    for dimension in sorted(rules.EXPLANATIONS):
        published = rules.PUBLISHED.get(dimension, "-")
        print(f"[{dimension}] published dialect: {published}")
        print(rules.explain(dimension))
        alternatives = [name for name in rules.DIALECTS[dimension] if name != published]
        print(f"  alternatives scored for sensitivity: {', '.join(alternatives)}")
        print()
    return 0


def _count() -> int:
    text = sys.stdin.read()
    for dimension, dialects in sorted(rules.DIALECTS.items()):
        if dimension == "items":
            continue
        counts = {dialect: rules.COUNTERS[dimension](text, dialect) for dialect in dialects}
        published = rules.PUBLISHED[dimension]
        spread = max(counts.values()) - min(counts.values())
        print(f"{dimension:<11} {counts[published]:>5} under {published:<18} "
              f"spread {spread:>3}  {counts}")
    return 0


def _answers() -> int:
    written = baselines.write_answers()
    print(f"wrote {len(written)} baseline answer files")
    return 0


def _report() -> int:
    built = report.build()
    print(report.as_text(built))
    return 0


def _board() -> int:
    print(report.as_text(report.load()))
    return 0


def _page() -> int:
    path = page.write()
    print(f"wrote {path.name}")
    return 0


def _fingerprint() -> int:
    print(fingerprint.digest())
    return 0


def _payload() -> int:
    json.dump(fingerprint.payload(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


COMMANDS = {"build": _build, "rules": _rules, "count": _count, "answers": _answers,
            "report": _report, "board": _board, "page": _page,
            "fingerprint": _fingerprint, "payload": _payload}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv or argv[0] not in COMMANDS:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return COMMANDS[argv[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
