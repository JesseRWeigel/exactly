"""Build the 500 prompts. Deterministic from one seed, and the rules travel inside the prompt.

The single most important line in this file is the one that puts `rules.explain(...)` into the
prompt text. A model cannot comply with a counting rule it was not told, and a benchmark that
withholds the rule and then reports which models "cannot count" is reporting its own tokenizer.
Every prompt here states, in the prompt, the exact rule its answer will be graded under.

Nine families, chosen so the leaderboard can separate things that are usually reported as one
number. Counting words is not the same problem as counting sentences, counting characters is
harder than either, and an upper bound is a different problem from an exact target: a system that
simply writes less than asked scores well on `sentences_at_most` and zero on `sentences_exact`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random

from . import corpus, rules

SEED = 20260829
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

# (family, dimension, mode, unique, how many, target range inclusive, form kind)
FAMILIES = (
    ("words_exact", "words", "exact", False, 80, (15, 120), "prose"),
    ("sentences_exact", "sentences", "exact", False, 70, (2, 8), "prose"),
    ("bullets_exact", "bullets", "exact", False, 70, (3, 12), "list"),
    ("unique_items", "bullets", "exact", True, 60, (5, 15), "list"),
    ("chars_exact", "chars", "exact", False, 50, (60, 300), "prose"),
    ("lines_exact", "lines", "exact", False, 45, (3, 10), "list"),
    ("paragraphs_exact", "paragraphs", "exact", False, 45, (2, 6), "block"),
    ("sentences_at_most", "sentences", "at_most", False, 40, (2, 6), "prose"),
    ("words_at_least", "words", "at_least", False, 40, (20, 100), "prose"),
)

NOUNS = {
    "words": "words", "sentences": "sentences", "bullets": "bullets",
    "chars": "characters", "lines": "lines", "paragraphs": "paragraphs",
}

HEADINGS = {
    "words": "HOW WORDS ARE COUNTED", "sentences": "HOW SENTENCES ARE COUNTED",
    "bullets": "HOW BULLETS ARE COUNTED", "chars": "HOW CHARACTERS ARE COUNTED",
    "lines": "HOW LINES ARE COUNTED", "paragraphs": "HOW PARAGRAPHS ARE COUNTED",
}

TAIL = ("Reply with the answer text only. Do not add a title, a preamble, a closing remark, "
        "or a count of your own.")


def constraint_text(dimension: str, mode: str, target: int, unique: bool) -> str:
    noun = NOUNS[dimension]
    if mode == "exact":
        body = f"exactly {target} {noun}"
    elif mode == "at_most":
        body = f"no more than {target} {noun}"
    elif mode == "at_least":
        body = f"at least {target} {noun}"
    else:
        raise ValueError(f"no such mode: {mode!r}")
    if unique:
        body += ", and no two of them may say the same thing"
    return body


def build_prompt(instruction: str, keyword: str, dimension: str, mode: str, target: int,
                 unique: bool) -> str:
    return "\n\n".join([
        instruction,
        f'Your answer must contain the word "{keyword}".',
        f"CONSTRAINT: {constraint_text(dimension, mode, target, unique)}.",
        f"{HEADINGS[dimension]}. Your answer is checked against this rule and no other:\n"
        + rules.explain(dimension, unique),
        TAIL,
    ])


def build() -> list:
    """Every item, in a fixed order, from the seed alone."""
    rng = random.Random(SEED)
    items = []
    for family, dimension, mode, unique, how_many, (low, high), form_kind in FAMILIES:
        forms = corpus.FORMS[form_kind]
        for index in range(how_many):
            topic, keyword = corpus.TOPICS[rng.randrange(len(corpus.TOPICS))]
            instruction = forms[rng.randrange(len(forms))].format(topic=topic)
            target = rng.randint(low, high)
            item_id = f"{family}-{index + 1:03d}"
            checks = ["count", "keyword"] + (["unique"] if unique else [])
            items.append({
                "id": item_id,
                "family": family,
                "dimension": dimension,
                "mode": mode,
                "target": target,
                "unique": unique,
                "topic": topic,
                "keyword": keyword,
                "checks": checks,
                "dialect": rules.PUBLISHED[dimension],
                "prompt": build_prompt(instruction, keyword, dimension, mode, target, unique),
            })
    return items


def manifest(items: list) -> dict:
    families = {}
    for item in items:
        row = families.setdefault(item["family"], {"n": 0, "targets": [10 ** 9, 0]})
        row["n"] += 1
        row["targets"][0] = min(row["targets"][0], item["target"])
        row["targets"][1] = max(row["targets"][1], item["target"])
    digest = hashlib.sha256()
    for item in items:
        digest.update(item["id"].encode())
        digest.update(item["prompt"].encode("utf-8"))
    return {
        "seed": SEED,
        "count": len(items),
        "families": families,
        "published_rules": dict(rules.PUBLISHED),
        "dialects": {dimension: list(found) for dimension, found in rules.DIALECTS.items()},
        "prompts_sha256": digest.hexdigest(),
    }


def write() -> tuple:
    items = build()
    DATA.mkdir(exist_ok=True)
    body = "".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in items)
    (DATA / "problems.jsonl").write_text(body, encoding="utf-8")
    (DATA / "dataset.json").write_text(
        json.dumps(manifest(items), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return items, manifest(items)


def load() -> tuple:
    path = DATA / "problems.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is missing; run `python3 -m exactly build`")
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    meta = json.loads((DATA / "dataset.json").read_text(encoding="utf-8"))
    return items, meta
