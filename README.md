# exactly

500 prompts with a precisely checkable count constraint, graded programmatically, with the
counting rules published, put inside the prompt, and their sensitivity measured.

Leaderboard: https://jesserweigel.github.io/exactly/

Catalog task: `EVAL-040`. One of a public catalog of build ideas:
https://github.com/JesseRWeigel/722-things-to-build

## What this is

"Write exactly 7 bullets." "Exactly 100 words." "Three sentences, no more." "A 12 item list with
no duplicates." Those are easy to ask for and easy to check, which makes them a clean test of
whether a model can count its own output. This repository is 500 such prompts across nine
families, a grader, a leaderboard, and the part that usually goes missing.

The part that usually goes missing is the definition of the number.

"Exactly 100 words" is undefined until somebody says whether `state-of-the-art` is one word or
four, whether `3.14` is a word, whether an emoji is, and what an em dash does to the tokens on
either side of it. "Three sentences" is undefined until somebody says what happens to `Dr. Smith`,
to `e.g.`, to `3.14`, to `1. First item`, and to a trailing fragment with no full stop on the end.
"Seven bullets" is undefined until somebody says whether a nested sub-bullet counts and whether a
numbered list is bullets at all. Every one of those questions has more than one defensible answer,
so a benchmark that picks one silently is grading models on its own tokenizer.

Three things follow, and they are the whole design.

**The rules are written down.** `exactly/rules.py` states each one longhand, in prose a person can
read and disagree with.

**The rules are in the prompt.** Every one of the 500 prompts carries, in the prompt, the exact
rule its answer will be graded under. A model cannot comply with a rule it was not told, and a
benchmark that hides the rule and then reports which models "cannot count" is reporting its own
splitter.

**The rules are varied and the effect is measured.** Each counter has alternative dialects, each
a defensible reading somebody else would have picked, and every system is scored again under each
of them. The spread is published beside the score.

## What the numbers say

Three things, and the last two were surprises.

**Models can count what they emit as units, and cannot count words or characters.** All three
models produce exactly the asked-for number of sentences between 87% and 99% of the time. All
three produce exactly the asked-for number of words between 1% and 6% of the time, and the
asked-for number of characters never, in 150 attempts. A bullet, a line, a paragraph and a
sentence are things a model finishes and starts. A word is a thing it has to keep a running total
of while it writes, and a character is worse. The families are kept apart on the leaderboard for
exactly this reason.

| family | what it asks for | gemma4:e4b | llama3.2:3b | qwen3.5:9b |
|---|---|---|---|---|
| `sentences_exact` | exactly N sentences | 98.6% | 87.1% | 97.1% |
| `paragraphs_exact` | exactly N paragraphs | 95.6% | 100.0% | 93.3% |
| `bullets_exact` | exactly N bullets | 95.7% | 87.1% | 85.7% |
| `words_at_least` | at least N words | 92.5% | 77.5% | 97.5% |
| `sentences_at_most` | no more than N sentences | 85.0% | 90.0% | 95.0% |
| `lines_exact` | exactly N lines | 93.3% | 88.9% | 48.9% |
| `unique_items` | N bullets, no repeats | 53.3% | 71.7% | 71.7% |
| `words_exact` | exactly N words | 1.2% | 6.2% | 2.5% |
| `chars_exact` | exactly N characters | 0.0% | 0.0% | 0.0% |

**Rule sensitivity turns out to be mostly a property of the system being measured.** This is the
number the project exists to report, and the honest version of it is more interesting than the one
that was expected. Swapping the word rule for `hyphen_split`, where `state-of-the-art` becomes
four words, moves gemma4:e4b and llama3.2:3b by 0.83 points across 120 items and qwen3.5:9b by
0.00. Swapping the sentence rule for a naive splitter that breaks at every full stop, including
the one in `Dr.`, moves the three models by 0.00, 1.82 and 0.00 points.

The same two swaps move the reference answers, which comply exactly, by 0.00 and 90.91 points, and
swapping the bullet rule to count nested sub-bullets moves them 53.85.

That is the finding. A system that hits the target on the nose sits on the rule boundary, so every
boundary decision changes its verdict. A model whose typical miss is 6 to 17 units is nowhere near
that boundary and is close to immune to which definition you picked. So the leaderboard here is
only slightly a measurement of the splitter, and the reason for that is unflattering to the
models. They are not close enough to the target for the definition to matter.

Two rules are exceptions and both are worth stating plainly.

**The character rule is the most sensitive thing in the project.** Counting code points takes the
reference answers to 100%. Counting only non-whitespace characters takes the same answers to 0%,
because every one was composed to hit a code point target with the spaces included. A 100 point
swing from one word of definition. "Exactly 200 characters" is close to meaningless as an
instruction unless the definition travels with it.

**The duplicate rule is the second.** Under the published reading, two list items are the same
item when they match after casefolding, dropping punctuation and collapsing whitespace. Under a
first-word reading, `red apples` and `red cars` are the same item, and compliance on that family
falls by 73 to 97 points for every system on the board. That reading is aggressive and it is on
the board precisely because somebody would pick it.

**Two of the three err low, and the third fails in a completely different shape.** Over the 420
exact-target items, llama3.2:3b undershoots 111 times against 36 overshoots, with 20% of its
misses off by exactly one and a long tail of 49 answers ten or more units short. gemma4:e4b is the
same shape, 115 under against 40 over, 18% off by one.

qwen3.5:9b is the opposite and is the most interesting row on the board. It is the most PRECISE of
the three when it is close, with 30% of its misses off by exactly one, and it is the only one that
fails catastrophically: 89 answers ten or more units over, of which 45 ran past a 4000 token
generation budget without stopping. Asked for exactly 36 words it produced 2646 and was still
going. Its median miss is 17 units where the others sit at 6 and 8, and its mean signed error is
+1187, which is a number about the runaways rather than about its aim. Off by one and off by two
thousand are different failures, a pass rate cannot tell them apart, and neither can a mean, so
every row carries a signed error and the report keeps the whole histogram and the median of the
misses beside it.

The signed error is reported over the exact-target families ALONE, and that correction flips the
sign of the headline. Pooling the bounds in made llama3.2:3b, which undershoots three times as
often as it overshoots, report a mean error of +1.25, because `at least 60 words` is satisfied by
140 and that counts as an error of +80 on a compliant answer. Over the exact targets alone the
same model reports -2.19, which is what it actually does.

## Baselines, because a benchmark with no baseline is a file

| system | what it does | compliance |
|---|---|---|
| `reference` | composes a correct answer from the rules | 100.0% |
| `filler_keyword` | emits the requested count of the word `item`, keyword dropped in | 100.0% |
| gemma4:e4b | a real model | 65.0% |
| llama3.2:3b | a real model | 64.4% |
| qwen3.5:9b | a real model | 62.8% |
| `approximate` | the reference, displaced by a deterministic amount | 10.4% |
| `filler` | the requested count of the word `item`, nothing else | 0.0% |
| `ignore` | one fixed paragraph, the same for every prompt | 0.0% |
| `off_by_one` | the reference, one unit out | 0.0% |
| `blank` | nothing at all | 0.0% |

`filler_keyword` is the number that matters most and it is deliberately unflattering to the
benchmark. Counting is mechanical. A program that understands nothing satisfies every check the
grader makes, so 100% is the ceiling on what compliance means here, and a model at 65% is 65% of
the way to a result that says nothing about whether it understood the question. The keyword
requirement in every prompt is a partial answer to this and the README says so rather than
pretending otherwise.

`off_by_one` scoring 0 on the count is the control that proves the grader is counting at all.
`reference` scoring 100 is the control that proves an answer can satisfy it. Both run on every
verify.

## Three things the measurements found

**`think: false` does not stop gpt-oss:20b reasoning, and the reasoning eats the whole budget.**
The first recording attempt produced answers like `Stonemasons rely on`, three words against a
target of twenty, which reads as a model with no idea how long its own output is. What actually
happened is that
it never finished the sentence. The server accepts `think: false`, echoes it back, and then
spends all 1200 tokens of the generation budget on a hidden reasoning channel that ollama strips
out of the response body. Measured: 4723 characters of hidden reasoning and 0 characters of
visible answer on one prompt, which at a 4000 token budget completes with 4934 hidden characters
and 721 visible ones. The transcript is in `fixtures/evidence/`. Every fixture row now records
`done_reason`, `eval_count` and `thinking_chars`, a row cut off at the budget is flagged, and
`exactly.recorded` refuses a fixture whose truncated share is over 10% rather than scoring it and
publishing a low number. gpt-oss:20b is off the leaderboard for this reason.

**The independent recount was wrong about three answers, and the cross-check found it.** The
package and the second implementation disagreed on 3 of gemma4:e4b's 500 responses. The checker
was the one at fault: it split tokens on whitespace and the ASCII hyphen only, so
`**horsehair**` sitting between two em dashes cleaned down to `horsehairis` and the required
keyword went missing. The published rule says an em dash separates the tokens on either side of
it, so both implementations now do. Three answers is 0.6% of one fixture, and a recount that
merely reported a total would have shown 322 against 325 with no way to see which three.

**The decimal guard in the sentence splitter was unreachable.** A sabotage that disabled the test
for a full stop between two digits could not move a single number in the fingerprint. The reason
is that a sentence cut already requires whitespace after the stop, and the stop in `3.14` is
followed by a digit, so the case was decided elsewhere and the guard was dead code. It was deleted
from both implementations rather than propped up, and the deletion was confirmed inert the same
way it was found: identical fingerprint, every test still passing.

## Running it

Python 3.10 or newer. Standard library only, no dependencies, nothing to install.

```bash
bash scripts/verify.sh              # the whole suite; its exit code is the result
python3 -m exactly rules            # the published counting rules, as the prompts state them
python3 -m exactly board            # the leaderboard as text
echo "Dr. Smith paid 3.14." | python3 -m exactly count   # one text, every dialect, side by side
python3 -m exactly report           # rebuild results/leaderboard.json from the committed fixtures
python3 -m exactly page             # rebuild docs/index.html from the leaderboard
python3 scripts/sabotage.py         # break the counting rules on purpose, three gates each
```

Recording a real model is separate and is the only thing here that opens a socket:

```bash
python3 scripts/record.py --model gemma4:e4b            # writes fixtures/responses/<model>.jsonl
python3 scripts/record.py --model qwen3.5:9b --num-predict 4000   # repairs truncated rows
```

`scripts/verify.sh` never runs it. The leaderboard is a function of the committed fixture bytes,
the prompts and the rules, all three of which are in git, so a verify run reproduces the same
numbers on a machine with no models on it.

## What is in here

```
exactly/rules.py         the counting rules, longhand, with every dialect
exactly/compose.py       the inverse: build text that satisfies a count exactly
exactly/generate.py      the 500 prompts, deterministic from one seed
exactly/grade.py         grade one response, aggregate a run, profile the errors
exactly/baselines.py     seven systems that answer without a model
exactly/recorded.py      read committed model answers, and refuse stale or truncated ones
exactly/report.py        the leaderboard and the rule sensitivity
exactly/fingerprint.py   one sha256 over the rules, the prompts and the grader
data/problems.jsonl      the dataset, one prompt per line, rules included in the prompt text
results/answers/         what every baseline actually said, so it can be checked from outside
results/leaderboard.json every number this project publishes
docs/index.html          the published page, generated from the leaderboard
```

## How it is checked

`scripts/verify.sh` is the gate and its exit code is the result. No step prints success for
something it did not run, and a step that cannot run is a failure rather than a skip.

- **158 unit tests.** Every counting decision is an assertion with the disagreeing reading named
  next to it, so the file doubles as the specification.
- **The reference control.** All 500 composed answers must be graded compliant, and the off-by-one
  variants must all fail. A grader nothing can satisfy is a bug that looks exactly like a hard
  benchmark.
- **26 sabotages under the three-gate rule**, each of which has to APPLY, MOVE the fingerprint,
  and THEN be caught. A null control runs first: an unchanged copy of the tree in a differently
  named directory must fingerprint identically, and the run is void if it does not. Five of the
  26 are guards, dormant code that cannot change a correct answer, so their requirement inverts to
  fingerprint unchanged and a checker failing anyway. An anchor that appears more than once in its
  file is refused rather than replaced.
- **An independent recount** that imports nothing from the package, proved by walking its own
  import graph with `ast` rather than by grep, against 11 probes that declare on their first line
  whether they must be accepted or refused. It reimplements the published rules from the rule text
  and recomputes the reference control, the baselines, every model total and the word sensitivity
  spread. The two implementations agree on all 500 composed answers and on every recorded model
  response.
- **A privacy scan** with 7 planted positive controls it must find and 5 negative controls it must
  ignore. One positive control hides a token behind a NUL byte, because `grep -I` treats such a
  file as binary and skips it while reporting the same "nothing found" as a real read.
- **A regeneration diff.** The dataset, the baseline answers, the leaderboard and the page are all
  rebuilt in a copy under `mktemp` and compared byte for byte, so nothing published here can go
  stale against the code that claims to produce it.
- **A mutation check.** Every tracked file is digested before the run and after it. A verify that
  edits the repository can pass on a later run for reasons an earlier run created.

## Status

Pasted from a real run of `bash scripts/verify.sh`, exit code 0. Re-running it reproduces this
block exactly; nothing variable is printed, no elapsed times and no temporary paths.

```
exactly: exact-count compliance, verify

     tracked files: 54
ok   the repository has a working tree to verify
ok   unit tests: 158 passed
ok   the suite is large enough to mean something
ok   every derived file regenerates byte for byte
  ok   regenerate build
  ok   regenerate answers
  ok   regenerate report
  ok   regenerate page
  ok   data/problems.jsonl matches the regenerated file
  ok   data/dataset.json matches the regenerated file
  ok   results/leaderboard.json matches the regenerated file
  ok   docs/index.html matches the regenerated file
  ok   results/answers: 7 file(s) match the regenerated form
ok   the fingerprint is stable across two runs
ok   the fingerprint does not depend on where the code lives
     fingerprint: fe3d23ea8c316fb0907ac549cf449ece0b7c8d4d3ef29c85c3980274c3b49cdb
ok   an independent recount agrees with every headline number
ok   the privacy scan finds its positive controls and nothing else
ok   no tracked file is larger than a megabyte
ok   the README exists
ok   the README carries a Status section
ok   the README carries a Unfinished section
ok   the README Status quotes this run's success line
ok   the README Status quotes this run's test count
ok   the README Status quotes this run's fingerprint
ok   the README prose has no scaffold markers left in it
ok   the README's own counts still match what they count
ok   the verify run did not modify the tree it verifies

steps passed: 18, failed: 0
VERIFY PASSED: exactly
```

## Unfinished

- **Three small local models, no frontier models.** The board holds gemma4:e4b, llama3.2:3b and
  qwen3.5:9b, all through ollama on one workstation. Nothing here has been run against a hosted
  model, so the leaderboard says what small open models do and cannot say what the constraint
  costs at the top of the range.
- **45 of qwen3.5:9b's 500 answers stopped at the generation budget, and 4 of those are in
  doubt.** They were recorded again at a 4000 token budget and ran past that too, with zero hidden
  reasoning, so the truncation is the model failing to stop rather than the harness running out of
  room. 41 of the 45 were already past their target when they stopped, which no amount of further
  text would have fixed. The remaining 4 were still short, and finishing them could have changed
  the verdict. The count is on the page next to the score.
- **gpt-oss:20b is measured but not scored.** It is the one reasoning model on this machine and
  the budget needed to get a usable recording out of it is several times any answer's length,
  which measures the harness rather than the model. The evidence file explains it.
- **The reference answers do not exercise the word dialects.** The filler vocabulary is plain
  ASCII with no hyphens, no digits and no dashes, which is why the reference scores identically
  under all four word readings. That was deliberate, so the composed answers could not become a
  test of the dialects, and the cost is that the word sensitivity for the reference is 0.0 and
  carries no information. The models' 0.83 points is the real figure.
- **One decision in `unwrap` is arbitrary and stays arbitrary.** The lenient reading strips a
  preamble line of at most 14 words. There is no principled threshold there. Both readings are
  reported and the difference between them is published as the packaging gap, which for both
  models is 0.0 points, so nothing currently rests on it.
- **The abbreviation list is closed and always will be.** There is no rule that separates `etc.`
  from `Ltd.` without a list, and a longer list would change the sentence counts. The list is in
  `exactly/rules.py`, it is in the fingerprint, and a change to it is visible in a diff.
- **The page is published and confirmed, the workflow's own verify run is the weaker claim.**
  `docs/index.html` is regenerated and diffed on every verify, the deployed page at
  https://jesserweigel.github.io/exactly/ was fetched back and is byte identical to the committed
  file, and the GitHub Actions run executes `scripts/verify.sh` on a clean ubuntu runner. What
  that does not cover is any browser behaviour: the page carries no script, so there is nothing to
  run and fail, and the markup is walked by a parser in the test suite rather than rendered.

## License

MIT.
