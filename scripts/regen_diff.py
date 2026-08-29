#!/usr/bin/env python3
"""Regenerate every derived file in a COPY and diff it against what is committed.

Two jobs in one script, which is why it exists rather than living inline in `verify.sh`.

  It stops a published artifact going quietly stale. The dataset, the baseline answers, the
  leaderboard and the page are all functions of the code and the committed fixtures. If any of
  them was generated once and then drifted, the repository would be publishing a number nothing
  in it can still produce.

  It is a catcher for `scripts/sabotage.py`. A sabotage of the counting rules changes what the
  leaderboard would be, and this is what notices that the committed one no longer matches.

The regeneration happens under `mktemp` and nothing in the source tree is written, so this can be
run against a tree that is being verified without becoming the reason the verify passes.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
STEPS = ("build", "answers", "report", "page")
TARGETS = ("data/problems.jsonl", "data/dataset.json", "results/leaderboard.json",
           "docs/index.html")
TREES = ("results/answers",)


def main() -> int:
    problems = []
    with tempfile.TemporaryDirectory() as holding:
        copy = pathlib.Path(holding) / "regen"
        shutil.copytree(ROOT, copy,
                        ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"))
        for step in STEPS:
            done = subprocess.run(["python3", "-m", "exactly", step], cwd=copy,
                                  capture_output=True, text=True)
            if done.returncode != 0:
                problems.append(f"`python3 -m exactly {step}` failed: "
                                f"{done.stderr.strip().splitlines()[-1] if done.stderr else ''}")
                print(f"  FAIL regenerate {step}")
                continue
            print(f"  ok   regenerate {step}")

        for target in TARGETS:
            here, there = ROOT / target, copy / target
            if not here.exists():
                problems.append(f"{target} is not committed, so there is nothing to compare")
                print(f"  FAIL {target} is missing from the tree")
                continue
            if not there.exists():
                problems.append(f"{target} was not regenerated")
                print(f"  FAIL {target} was not regenerated")
                continue
            if here.read_bytes() != there.read_bytes():
                problems.append(f"committed {target} differs from what the code regenerates")
                print(f"  FAIL {target} differs from the regenerated file")
                continue
            print(f"  ok   {target} matches the regenerated file")

        for tree in TREES:
            here, there = ROOT / tree, copy / tree
            names = sorted(path.name for path in here.glob("*")) if here.is_dir() else []
            other = sorted(path.name for path in there.glob("*")) if there.is_dir() else []
            if not names or names != other:
                problems.append(f"{tree} does not hold the same files after regeneration")
                print(f"  FAIL {tree} file list differs")
                continue
            differing = [name for name in names
                         if (here / name).read_bytes() != (there / name).read_bytes()]
            if differing:
                problems.append(f"{tree}: {', '.join(differing)} differ from the regenerated form")
                print(f"  FAIL {tree}: {len(differing)} file(s) differ")
                continue
            print(f"  ok   {tree}: {len(names)} file(s) match the regenerated form")

    if problems:
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print(f"REGENERATION DIFF FAILED: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print("REGENERATION DIFF CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
