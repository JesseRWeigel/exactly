#!/usr/bin/env python3
"""Ask a real model the 500 prompts and write its answers into a fixture file.

THIS IS THE ONLY FILE IN THE PROJECT THAT OPENS A SOCKET, and that separation is the point. A
model call is not a measurement: sampling is not reproducible, a server can be busy, a model can
be swapped out from under you, and none of that may reach the numbers a verify run reports. So
the split is enforced by construction:

  This script talks to Ollama and writes `fixtures/responses/<model>.jsonl`, which is committed.
  Everything that grades, scores, sabotages or verifies reads those committed files and opens
  nothing. `scripts/verify.sh` never runs this, and the leaderboard is a function of the fixture
  bytes, the prompts and the rules, all three of which are in git.

Usage:
    python3 scripts/record.py --model gpt-oss:20b [--limit 500] [--host http://localhost:11434]

Options are set for the least sampling variation available: temperature 0, top_p 1, a fixed seed
and an explicit `num_ctx`, which per this workstation's notes is the ONLY setting that actually
changes the loaded context length. Hidden reasoning is switched OFF where the server accepts it,
because a run that leaves it on is measuring a different system than the one it names.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exactly import generate  # noqa: E402

OUT = ROOT / "fixtures" / "responses"


def call(host: str, model: str, prompt: str, think, timeout: int):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "top_p": 1, "seed": 7, "num_ctx": 4096,
                    "num_predict": 1200},
    }
    if think is not None:
        body["think"] = think
    request = urllib.request.Request(
        host.rstrip("/") + "/api/chat", method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as handle:
        return json.loads(handle.read().decode("utf-8"))


def negotiate(host: str, model: str, timeout: int):
    """Find the strongest `think` setting the server will accept for this model."""
    for candidate in (False, "low", None):
        try:
            call(host, model, "Say the word ok.", candidate, timeout)
            return candidate
        except urllib.error.HTTPError as problem:
            detail = problem.read().decode("utf-8", "replace")[:200]
            print(f"  think={candidate!r} refused: {detail}", file=sys.stderr)
    raise SystemExit(f"{model} would not answer at all")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    items, _ = generate.load()
    if args.limit:
        items = items[:args.limit]
    think = negotiate(args.host, args.model, args.timeout)
    print(f"{args.model}: think={think!r}, {len(items)} prompts", file=sys.stderr)

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / (args.model.replace(":", "_").replace("/", "_") + ".jsonl")
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row
    started = time.time()
    with path.open("w", encoding="utf-8") as handle:
        for index, item in enumerate(items, start=1):
            row = done.get(item["id"])
            if row is None or row.get("error"):
                try:
                    reply = call(args.host, args.model, item["prompt"], think, args.timeout)
                    row = {"id": item["id"], "model": args.model,
                           "prompt_sha256": hashlib.sha256(
                               item["prompt"].encode("utf-8")).hexdigest(),
                           "response": reply.get("message", {}).get("content", ""),
                           "think": think if think is not None else "default"}
                except Exception as problem:                    # noqa: BLE001
                    row = {"id": item["id"], "model": args.model,
                           "prompt_sha256": hashlib.sha256(
                               item["prompt"].encode("utf-8")).hexdigest(),
                           "response": "", "error": repr(problem)[:200]}
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 25 == 0:
                rate = (time.time() - started) / index
                print(f"  {index}/{len(items)} at {rate:.1f}s each", file=sys.stderr, flush=True)
    print(f"wrote {path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
