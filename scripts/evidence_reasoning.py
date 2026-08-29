#!/usr/bin/env python3
"""Measure what `think: false` actually buys, and write the transcript to a committed file.

This exists because of a finding that nearly went into the leaderboard as a fact about counting.

Recording gpt-oss:20b with `think: false` produced answers like `Stonemasons rely on`, three words
against a target of twenty. Read at face value that is a model with no idea how long its own
output is. It is a model that never finished the sentence: the server accepted `think: false`,
echoed it back, and then spent the entire 1200 token generation budget on a hidden reasoning
channel that ollama strips out of the response body. The visible answer is whatever happened to
be emitted before the budget ran out, which is usually nothing.

A benchmark that grades those responses is reporting its own `num_predict`. So every fixture row
in this project records `done_reason`, `eval_count` and `thinking_chars`, a row cut off at the
budget is flagged, and `exactly.recorded` refuses to score a fixture whose truncated share is
above a threshold. This script is the evidence behind those three decisions.

It opens a socket, so it is never run by `scripts/verify.sh`. Run it by hand:

    python3 scripts/evidence_reasoning.py --model gpt-oss:20b
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exactly import generate  # noqa: E402

OUT = ROOT / "fixtures" / "evidence"
BUDGETS = (1200, 4000)


def call(host: str, model: str, prompt: str, think, num_predict: int, timeout: int) -> dict:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
            "think": think,
            "options": {"temperature": 0, "top_p": 1, "seed": 7, "num_ctx": 8192,
                        "num_predict": num_predict}}
    request = urllib.request.Request(host.rstrip("/") + "/api/chat", method="POST",
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as handle:
        reply = json.loads(handle.read().decode("utf-8"))
    message = reply.get("message", {})
    return {
        "seconds": round(time.time() - started, 1),
        "done_reason": reply.get("done_reason", ""),
        "eval_count": reply.get("eval_count", 0),
        "thinking_chars": len(message.get("thinking") or ""),
        "content": message.get("content", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    items, _ = generate.load()
    chosen = items[:args.count]
    rows = []
    for item in chosen:
        for budget in BUDGETS:
            result = call(args.host, args.model, item["prompt"], False, budget, args.timeout)
            result.update({"id": item["id"], "num_predict": budget, "think": False,
                           "target": item["target"], "dimension": item["dimension"]})
            rows.append(result)
            print(f"{item['id']} budget {budget}: {result['done_reason']}, "
                  f"{result['eval_count']} tokens, {result['thinking_chars']} hidden chars, "
                  f"{len(result['content'])} visible chars", file=sys.stderr, flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# `think: false` does not stop {args.model} reasoning",
        "",
        "Produced by `python3 scripts/evidence_reasoning.py`. Not run by `scripts/verify.sh`,",
        "which never opens a socket.",
        "",
        f"Each prompt below was sent twice to `{args.model}` through ollama's `/api/chat`, with",
        "`think: false` both times and nothing else changed except `num_predict`. The server",
        "accepts the flag and echoes it back. `hidden` is the length of the `thinking` field that",
        "ollama strips out of the response body; `visible` is the answer a benchmark would grade.",
        "",
        "| item | dimension | target | budget | stop reason | tokens | hidden | visible | first 60 chars |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        preview = row["content"][:60].replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| {row['id']} | {row['dimension']} | {row['target']} | {row['num_predict']} | "
            f"{row['done_reason']} | {row['eval_count']} | {row['thinking_chars']} | "
            f"{len(row['content'])} | `{preview}` |")

    cut = [row for row in rows if row["done_reason"] == "length"]
    lines += [
        "",
        "## What this changes",
        "",
        f"{len(cut)} of {len(rows)} calls stopped because they ran out of budget rather than",
        "because the model had finished. Every one of those has a hidden reasoning channel longer",
        "than the visible answer, so the text a grader would score is a fragment.",
        "",
        "Three things in this repository follow from it:",
        "",
        "- `scripts/record.py` stores `done_reason`, `eval_count` and `thinking_chars` on every",
        "  row, and flags a row that stopped at the budget as `truncated`.",
        "- `exactly.recorded` refuses a fixture whose truncated share is above",
        "  `TRUNCATION_LIMIT`, rather than scoring it and reporting a low number.",
        "- Raising `--num-predict` re-asks only the rows that were cut off at a smaller budget,",
        "  so a fixture can be repaired without re-recording the whole run.",
        "",
        f"{args.model} is not on the leaderboard for this reason. Getting a usable recording of it",
        "means a budget several times larger than any answer needs, which is a measurement of the",
        "harness rather than of the model, and the honest place for it is here.",
        "",
    ]
    path = OUT / (args.model.replace(":", "_").replace("/", "_") + "-hidden-reasoning.md")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
