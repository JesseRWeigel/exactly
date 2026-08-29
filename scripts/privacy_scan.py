#!/usr/bin/env python3
"""Look for credentials and personal paths in the tracked tree, and prove the looking works.

Three failure modes this is built against, each of which has bitten a project in this fleet.

  A SCANNER THAT READS NOTHING IS SILENT IN EXACTLY THE SAME WAY AS A CLEAN TREE. So there are
  planted POSITIVE CONTROLS, credential-shaped strings the scanner is required to find, and the
  scan fails if it misses one. There are also NEGATIVE CONTROLS, strings that look alarming and
  are not, which the scanner is required NOT to flag, because a scanner that flags everything is
  as useless as one that flags nothing and takes longer to ignore.

  ONE NUL BYTE MAKES grep BLIND TO A WHOLE FILE. `grep -I` and `git grep -I` classify a file
  containing a NUL as binary and skip it entirely, reporting the same "nothing found" as a real
  read. Every file here is read as BYTES by Python and decoded with `errors="replace"`, so a NUL
  hides nothing. One positive control is a NUL-bearing blob with a token inside it, which is what
  proves that claim rather than asserting it.

  A SCANNER MATCHES ITS OWN PATTERN LIST. Every pattern below is assembled from fragments at
  import time, so the literal text of a key prefix never appears in this file, and the scan can
  read its own source without finding itself.

The positive controls are synthetic sources passed to the scanner in memory, not files written
into the tree. A verify run must not modify the tree it verifies, and a scanner that writes a
fake key into the working directory to test itself is one interrupted run away from committing it.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Below this many tracked files the scan is not measuring the repository. Before the first commit
# `git ls-files` returns nothing at all and a scan of nothing passes without opening a file.
MINIMUM_TRACKED = 20


def _join(*fragments: str) -> str:
    return "".join(fragments)


# Patterns, each assembled so its literal form is absent from this source. Case matters where the
# real format is case sensitive: AWS key ids are uppercase by definition, and a case insensitive
# match for one false-positives on ordinary base64, which is how an embedded image became an alarm
# in another project here.
PATTERNS = (
    ("aws access key id", re.compile(_join("AK", "IA") + r"[0-9A-Z]{16}")),
    ("github personal access token", re.compile(_join("gh", "p_") + r"[A-Za-z0-9]{36}")),
    ("github fine grained token", re.compile(_join("github", "_pat_") + r"[A-Za-z0-9_]{22,}")),
    ("openai style api key", re.compile(_join("sk", "-") + r"[A-Za-z0-9]{20,}")),
    ("openrouter key", re.compile(_join("sk", "-or-v1-") + r"[A-Za-z0-9]{32,}")),
    ("slack token", re.compile(_join("xox", "[baprs]-") + r"[A-Za-z0-9-]{10,}")),
    ("google api key", re.compile(_join("AI", "za") + r"Sy[A-Za-z0-9_\-]{33}")),
    ("private key block", re.compile(_join("-----BEGIN ", "([A-Z ]+ )?PRIVATE KEY", "-----"))),
    ("bearer token in a header", re.compile(_join("Authorization", r":\s*Bearer\s+")
                                            + r"[A-Za-z0-9._\-]{20,}")),
    ("home directory path", re.compile(_join("/home/", r"(?!<user>|USER\b)[a-z][a-z0-9_-]{2,}/"))),
    ("password assignment", re.compile(_join("pass", "word") + r"\s*[=:]\s*[\"'][^\"']{6,}[\"']",
                                       re.IGNORECASE)),
)

# Strings that look alarming and are not. Each one is a false positive some scanner has produced.
NEGATIVE_CONTROLS = (
    ("base64 blob resembling an aws id in mixed case",
     b"iVBORw0KGgoAkiAqaMkgIem1yaUXNKiJ2MoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"),
    ("prose about secrets",
     b"No secrets in git. Never commit a password. The token is read from the environment."),
    ("an env example line with a placeholder",
     b"OPENAI_API_KEY=your-key-here\nOLLAMA_HOST=http://localhost:11434\n"),
    ("a documented home path with a placeholder user",
     b"the transcript lives at /home/<user>/projects/exactly/results\n"),
    ("a short sk word in ordinary prose", b"the risk-free rate and the sk of a distribution"),
)


def positive_controls() -> tuple:
    """Credential-shaped strings the scanner MUST find, assembled here rather than stored.

    Nothing in this file, and nothing on disk, holds a complete credential-shaped string. GitHub's
    push protection scans full history and rejects a push containing one even when it is fake, and
    a later fix does not help because the object is already in the history. Assembling them at run
    time keeps the tree clean and the control real.
    """
    return (
        ("aws key", (_join("AK", "IA") + "ABCDEFGHIJKLMNOP").encode()),
        ("github token", (_join("gh", "p_") + "a" * 36).encode()),
        ("openai key", (_join("sk", "-") + "B" * 40).encode()),
        ("private key header", _join("-----BEGIN ", "RSA PRIVATE KEY", "-----").encode()),
        ("bearer header", (_join("Authorization", ": Bearer ") + "x" * 32).encode()),
        # Assembled like the rest. Written out whole it would be a real hit in this very file,
        # which is the scanner matching its own test data and not a finding about the repository.
        ("home path", ("see " + _join("/home/", "someuser")
                       + "/projects/notes.txt for the transcript").encode()),
        # The whole point of this one: a NUL makes grep call the file binary and skip it, so a
        # scanner built on `grep -I` reports this blob clean while the token sits in the middle.
        ("token behind a NUL byte",
         b"header\x00binary\x00" + (_join("gh", "p_") + "b" * 36).encode() + b"\x00tail"),
    )


def findings(label: str, blob: bytes) -> list:
    text = blob.decode("utf-8", errors="replace")
    found = []
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            found.append((label, name, match.group()[:12] + "..."))
    return found


def tracked_files() -> list:
    """Every file git is tracking, read as bytes. No file type is skipped."""
    output = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                            capture_output=True, check=True).stdout
    names = [name for name in output.decode().split("\0") if name]
    made = []
    for name in names:
        path = ROOT / name
        if path.is_file():
            made.append((name, path.read_bytes()))
    return made


def main() -> int:
    problems = []

    missed = [label for label, blob in positive_controls() if not findings(label, blob)]
    if missed:
        problems.append(f"positive control(s) NOT detected: {', '.join(missed)}. The scanner is "
                        f"not reading what it claims to read, so its clean result means nothing.")
    print(f"positive controls: {len(positive_controls()) - len(missed)}"
          f"/{len(positive_controls())} detected")

    noisy = [(label, found) for label, blob in NEGATIVE_CONTROLS
             for found in [findings(label, blob)] if found]
    if noisy:
        for label, found in noisy:
            problems.append(f"negative control {label!r} was flagged as {found[0][1]}")
    print(f"negative controls: {len(NEGATIVE_CONTROLS) - len(noisy)}"
          f"/{len(NEGATIVE_CONTROLS)} correctly ignored")

    files = tracked_files()
    if len(files) < MINIMUM_TRACKED:
        problems.append(f"only {len(files)} tracked file(s), below the minimum of "
                        f"{MINIMUM_TRACKED}. Commit before scanning; a scan of an empty index "
                        f"passes without opening anything.")
    print(f"tracked files scanned: {len(files)}")

    hits = [hit for name, blob in files for hit in findings(name, blob)]
    for name, kind, sample in hits:
        problems.append(f"{name}: {kind} matching {sample}")

    for line in problems:
        print(f"  FAIL {line}", file=sys.stderr)
    if problems:
        print(f"PRIVACY SCAN FAILED: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print("PRIVACY SCAN CLEAN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
