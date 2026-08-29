# `think: false` does not stop gpt-oss:20b reasoning

Produced by `python3 scripts/evidence_reasoning.py`. Not run by `scripts/verify.sh`,
which never opens a socket.

Each prompt below was sent twice to `gpt-oss:20b` through ollama's `/api/chat`, with
`think: false` both times and nothing else changed except `num_predict`. The server
accepts the flag and echoes it back. `hidden` is the length of the `thinking` field that
ollama strips out of the response body; `visible` is the answer a benchmark would grade.

| item | dimension | target | budget | stop reason | tokens | hidden | visible | first 60 chars |
|---|---|---|---|---|---|---|---|---|
| words_exact-001 | words | 99 | 1200 | length | 1200 | 4723 | 0 | `` |
| words_exact-001 | words | 99 | 4000 | stop | 1403 | 4934 | 721 | `Stonemasons rely on a variety of specialized tools that blen` |
| words_exact-002 | words | 22 | 1200 | stop | 587 | 2280 | 164 | `Johannes Gutenberg invented the movable type printing press ` |
| words_exact-002 | words | 22 | 4000 | stop | 587 | 2280 | 164 | `Johannes Gutenberg invented the movable type printing press ` |
| words_exact-003 | words | 19 | 1200 | stop | 424 | 1417 | 109 | `Sourdough starter stays alive by daily feeding with fresh fl` |
| words_exact-003 | words | 19 | 4000 | stop | 506 | 1862 | 115 | `Sourdough starter stays alive by daily feeding with fresh fl` |
| words_exact-004 | words | 35 | 1200 | stop | 698 | 2483 | 255 | `Before the 15th century, manuscripts were copied by hand, a ` |
| words_exact-004 | words | 35 | 4000 | stop | 802 | 2576 | 242 | `Before the 15th century, books were copied by hand, a slow a` |
| words_exact-005 | words | 86 | 1200 | length | 1200 | 4974 | 0 | `` |
| words_exact-005 | words | 86 | 4000 | stop | 1548 | 5733 | 526 | `Crafting a violin bow begins with selecting the finest perna` |
| words_exact-006 | words | 36 | 1200 | stop | 972 | 3460 | 230 | `Light enters a camera lens, curves across its curved surface` |
| words_exact-006 | words | 36 | 4000 | stop | 972 | 3460 | 230 | `Light enters a camera lens, curves across its curved surface` |

## What this changes

2 of 12 calls stopped because they ran out of budget rather than
because the model had finished. On the narrowest of those the hidden reasoning channel
is 4723 characters longer than the visible answer, so the text a grader would score
is a fragment of a sentence.

Three things in this repository follow from it:

- `scripts/record.py` stores `done_reason`, `eval_count` and `thinking_chars` on every
  row, and flags a row that stopped at the budget as `truncated`.
- `exactly.recorded` refuses a fixture whose truncated share is above
  `TRUNCATION_LIMIT`, rather than scoring it and reporting a low number.
- Raising `--num-predict` re-asks only the rows that were cut off at a smaller budget,
  so a fixture can be repaired without re-recording the whole run.

gpt-oss:20b is not on the leaderboard for this reason. Getting a usable recording of it
means a budget several times larger than any answer needs, which is a measurement of the
harness rather than of the model, and the honest place for it is here.
