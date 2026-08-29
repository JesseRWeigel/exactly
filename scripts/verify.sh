#!/usr/bin/env bash
# The exit code of this script IS the result. Nothing prints success for a step it did not run.
#
# Three rules govern everything below.
#
#   A STEP THAT CANNOT RUN IS A FAILURE. Not a skip, not a warning. A skipped check and a passing
#   check are indistinguishable in a log a week later, so a missing dependency, a missing file or
#   an unreachable service all exit nonzero with a message that names the fix.
#
#   THIS SCRIPT DOES NOT MODIFY THE TREE IT VERIFIES. Every regeneration happens in a copy under
#   a temporary directory and is diffed against the committed files. The digest of every tracked
#   file is taken at the start and compared at the end, and a difference is a named failure. A
#   verify that edits the repository can pass on a later run for reasons an earlier run created.
#
#   NOTHING VARIABLE IS PRINTED. No elapsed times, no temporary paths, no timestamps. The output
#   is pasted into the README and has to reproduce exactly on a fresh run, so anything that
#   changes between two identical runs would mean the README could never converge.
#
# It never contacts a model. Recording is `scripts/record.py`, it is run by hand, and its output
# is committed. The leaderboard is a function of files in git.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

SLUG="exactly"
PASSED=0
FAILED=0
FAILURES=""

command -v python3 > /dev/null 2>&1 || {
  echo "FAIL python3 is not on PATH. Install python 3.10 or newer; the whole suite is stdlib." >&2
  exit 2
}
command -v git > /dev/null 2>&1 || {
  echo "FAIL git is not on PATH. The privacy scan and the tree digest both read the index." >&2
  exit 2
}

# Per run, from mktemp, and never a shared path. A builder in this fleet redirected a verify
# transcript to a shared scratchpad while other agents were running and read back another
# project's output spliced into the middle of a line.
WORK="$(mktemp -d)" || exit 2
trap 'rm -rf "$WORK"' EXIT

step() {
  local label="$1"; shift
  if "$@" > "$WORK/step.log" 2>&1; then
    PASSED=$((PASSED + 1))
    printf 'ok   %s\n' "$label"
    return 0
  fi
  FAILED=$((FAILED + 1))
  FAILURES="${FAILURES}
  - ${label}"
  printf 'FAIL %s\n' "$label"
  sed 's/^/       /' "$WORK/step.log" | tail -25
  return 1
}

note() { printf '     %s\n' "$1"; }

echo "exactly: exact-count compliance, verify"
echo

# ---------------------------------------------------------------------------------------------
# 1. the tree digest, taken before anything runs
# ---------------------------------------------------------------------------------------------
tree_digest() {
  git ls-files -z | sort -z | xargs -0 -r sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1
}
BEFORE="$(tree_digest)"
TRACKED="$(git ls-files | wc -l | tr -d ' ')"
note "tracked files: ${TRACKED}"

step "the repository has a working tree to verify" test "${TRACKED}" -ge 20

# ---------------------------------------------------------------------------------------------
# 2. the unit suite
# ---------------------------------------------------------------------------------------------
if python3 -m unittest discover -s tests -t . > "$WORK/unit.log" 2>&1; then
  TESTS="$(grep -oE '^Ran [0-9]+ test' "$WORK/unit.log" | grep -oE '[0-9]+')"
  PASSED=$((PASSED + 1))
  printf 'ok   unit tests: %s passed\n' "$TESTS"
else
  TESTS="0"
  FAILED=$((FAILED + 1))
  FAILURES="${FAILURES}
  - unit tests"
  printf 'FAIL unit tests\n'
  sed 's/^/       /' "$WORK/unit.log" | tail -40
fi

step "the suite is large enough to mean something" test "${TESTS:-0}" -ge 100

# ---------------------------------------------------------------------------------------------
# 3. the derived files regenerate byte for byte, in a COPY, so this tree is not touched
# ---------------------------------------------------------------------------------------------
# One script does this, and `scripts/sabotage.py` uses the same one as a catcher, so the two
# cannot drift apart. It regenerates under mktemp and writes nothing into this tree.
regen_report() { python3 scripts/regen_diff.py; }
if regen_report > "$WORK/regen.log" 2>&1; then
  PASSED=$((PASSED + 1))
  printf 'ok   every derived file regenerates byte for byte\n'
  sed 's/^/     /' "$WORK/regen.log" | grep -E 'ok   ' | sed 's/^     //'
else
  FAILED=$((FAILED + 1))
  FAILURES="${FAILURES}
  - the derived files no longer regenerate"
  printf 'FAIL every derived file regenerates byte for byte\n'
  sed 's/^/       /' "$WORK/regen.log" | tail -30
fi

mkdir -p "$WORK/regen"
tar -cf - --exclude=.git --exclude=__pycache__ . 2>/dev/null | tar -xf - -C "$WORK/regen"

# ---------------------------------------------------------------------------------------------
# 4. the fingerprint, which is what the sabotage harness measures
# ---------------------------------------------------------------------------------------------
FINGERPRINT="$(python3 -m exactly fingerprint 2>/dev/null)"
AGAIN="$(python3 -m exactly fingerprint 2>/dev/null)"
step "the fingerprint is stable across two runs" test -n "$FINGERPRINT" -a "$FINGERPRINT" = "$AGAIN"
FROM_COPY="$( cd "$WORK/regen" && python3 -m exactly fingerprint 2>/dev/null )"
step "the fingerprint does not depend on where the code lives" \
  test "$FINGERPRINT" = "$FROM_COPY"
note "fingerprint: ${FINGERPRINT}"

# ---------------------------------------------------------------------------------------------
# 5. the independent recount and the privacy scan
# ---------------------------------------------------------------------------------------------
step "an independent recount agrees with every headline number" \
  python3 scripts/check_independent.py
step "the privacy scan finds its positive controls and nothing else" \
  python3 scripts/privacy_scan.py

# ---------------------------------------------------------------------------------------------
# 6. the repository hygiene checks
# ---------------------------------------------------------------------------------------------
big_files() {
  local found
  found="$(git ls-files -z | xargs -0 -r du -k 2>/dev/null | awk '$1 > 1024 {print $2, $1"k"}')"
  if [ -n "$found" ]; then echo "$found"; return 1; fi
  return 0
}
step "no tracked file is larger than a megabyte" big_files

step "the README exists" test -f README.md
step "the README carries a Status section" grep -q '^## Status' README.md
step "the README carries a Unfinished section" grep -q '^## Unfinished' README.md
step "the README Status quotes this run's success line" \
  grep -qF "VERIFY PASSED: ${SLUG}" README.md
step "the README Status quotes this run's test count" \
  grep -qF "unit tests: ${TESTS} passed" README.md
step "the README Status quotes this run's fingerprint" grep -qF "${FINGERPRINT}" README.md

# A scaffold marker search matches its own transcript inside the Status block, so the prose is
# read with the fenced blocks removed rather than by excluding the word, which would disarm the
# check exactly where it is tested.
prose_only() {
  python3 - "$@" <<'PYTHON'
import pathlib, re, sys
text = pathlib.Path("README.md").read_text(encoding="utf-8")
prose = re.sub(r"(?ms)^```.*?^```\s*$", "", text)
markers = [word for word in ("TODO", "FIXME", "XXX", "replace with a real")
           if word in prose]
if markers:
    print("scaffold marker(s) left in the README prose: " + ", ".join(markers))
    sys.exit(1)
sys.exit(0)
PYTHON
}
step "the README prose has no scaffold markers left in it" prose_only

# Every count the README states about itself, checked against the thing it counts. A pasted
# "144 unit tests" goes stale the moment somebody adds a test, and it did: the prose said 144
# while the Status block said 158, and nothing noticed until a human read both.
readme_counts() {
  python3 - "$TESTS" <<'PYTHON'
import importlib.util, pathlib, sys

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

sabotage = load("scripts/sabotage.py", "sabotage_under_check")
privacy = load("scripts/privacy_scan.py", "privacy_under_check")
readme = pathlib.Path("README.md").read_text(encoding="utf-8")

claims = [
    (f"**{int(sys.argv[1])} unit tests.**", "the unit suite's size"),
    (f"**{len(sabotage.SABOTAGES)} sabotages under the three-gate rule**", "the sabotage count"),
    (f"against {len(list(pathlib.Path('scripts/probes').glob('*.py')))} probes",
     "the probe count"),
    (f"{len(privacy.positive_controls())} planted positive controls", "the positive controls"),
    (f"{len(privacy.NEGATIVE_CONTROLS)} negative controls", "the negative controls"),
]
missing = [why for phrase, why in claims if phrase not in readme]
for phrase, why in claims:
    if phrase not in readme:
        print(f"the README no longer states {why} correctly; expected the phrase {phrase!r}")
sys.exit(1 if missing else 0)
PYTHON
}
step "the README's own counts still match what they count" readme_counts

# ---------------------------------------------------------------------------------------------
# 7. the tree is exactly as it was found
# ---------------------------------------------------------------------------------------------
AFTER="$(tree_digest)"
step "the verify run did not modify the tree it verifies" test "$BEFORE" = "$AFTER"

echo
echo "steps passed: ${PASSED}, failed: ${FAILED}"
if [ "$FAILED" -ne 0 ]; then
  printf 'VERIFY FAILED: %s%s\n' "$SLUG" "$FAILURES"
  exit 1
fi
echo "VERIFY PASSED: ${SLUG}"
exit 0
