"""Generate `docs/index.html` from `results/leaderboard.json`. No numbers are typed by hand.

The page is a pure function of the results file, and `scripts/verify.sh` rebuilds it and diffs
the bytes, so a published page cannot quietly go stale while the data underneath it changes.
Everything is inlined, and there is no script, because a page that needs JavaScript to show a
table is a page that can render blank and still pass a file-exists check.
"""

from __future__ import annotations

import html
import pathlib

from . import report

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"

STYLE = """
:root { color-scheme: light dark; --ink: #16181d; --dim: #5b6472; --line: #d8dce4;
        --bg: #fbfbfc; --panel: #ffffff; --good: #1a7f4b; --bad: #a3341f; --warn: #8a6d1f; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #e8eaf0; --dim: #99a2b3; --line: #333a47; --bg: #14161a; --panel: #1c1f26;
          --good: #57c98a; --bad: #e08268; --warn: #d9b55c; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1.25rem 4rem; background: var(--bg); color: var(--ink);
       font: 16px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 62rem; margin: 0 auto; }
h1 { font-size: 1.9rem; margin: 0 0 .3rem; letter-spacing: -.01em; }
h2 { font-size: 1.15rem; margin: 2.4rem 0 .6rem; }
h3 { font-size: .95rem; margin: 1.6rem 0 .4rem; font-weight: 600; }
h3 span { color: var(--dim); font-weight: 400; font-size: .82rem; }
p { max-width: 46rem; }
.sub { color: var(--dim); margin: 0 0 1.6rem; }
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px;
          background: var(--panel); }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums;
        font-size: .92rem; }
th, td { padding: .5rem .7rem; text-align: right; border-bottom: 1px solid var(--line);
         white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
thead th { font-weight: 600; color: var(--dim); font-size: .8rem; text-transform: uppercase;
           letter-spacing: .04em; }
tbody tr:last-child td { border-bottom: 0; }
tr.baseline td:first-child { color: var(--dim); }
.good { color: var(--good); } .bad { color: var(--bad); } .warn { color: var(--warn); }
.cards { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
         margin: 1.5rem 0; }
.card { border: 1px solid var(--line); border-radius: 8px; padding: .85rem 1rem;
        background: var(--panel); }
.card b { display: block; font-size: 1.6rem; font-weight: 650; letter-spacing: -.02em; }
.card span { color: var(--dim); font-size: .84rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
footer { color: var(--dim); font-size: .85rem; margin-top: 3rem; }
"""


def _pct(value) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _cell(text, klass=None) -> str:
    attr = f' class="{klass}"' if klass else ""
    return f"<td{attr}>{html.escape(str(text))}</td>"


def _leaderboard_table(systems: list) -> str:
    head = ("<tr><th>system</th><th>kind</th><th>compliant</th><th>count ok</th>"
            "<th>keyword ok</th><th>mean error</th><th>off by one</th>"
            "<th>worst rule swing</th></tr>")
    rows = []
    for board in sorted(systems, key=lambda item: -item["strict"]["overall"]["rate"]):
        overall = board["strict"]["overall"]
        errors = overall["errors"]
        worst = board["sensitivity"]["worst"]
        swing = (f"{worst['spread_points']:.1f} pt ({worst['dimension']})"
                 if worst["dimension"] else "none")
        share = errors["off_by_one_share_of_misses"]
        klass = "good" if overall["rate"] >= 0.9 else ("bad" if overall["rate"] < 0.2 else "warn")
        rows.append(
            f'<tr class="{board["kind"]}">'
            + _cell(board["system"]) + _cell(board["kind"])
            + _cell(_pct(overall["rate"]), klass)
            + _cell(f"{overall['count_ok']}/{overall['n']}")
            + _cell(f"{overall['keyword_ok']}/{overall['n']}")
            + _cell("-" if errors["mean_error"] is None else f"{errors['mean_error']:+.2f}")
            + _cell("-" if share is None else f"{share * 100:.0f}%")
            + _cell(swing) + "</tr>")
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(rows)}' \
           "</tbody></table></div>"


def _family_table(systems: list, families: dict) -> str:
    names = sorted(families)
    head = "<tr><th>system</th>" + "".join(
        f"<th>{html.escape(name)}<br><span>{families[name]}</span></th>" for name in names
    ) + "</tr>"
    rows = []
    for board in sorted(systems, key=lambda item: -item["strict"]["overall"]["rate"]):
        cells = []
        for name in names:
            row = board["strict"]["families"].get(name)
            value = row["rate"] if row else None
            klass = None
            if value is not None:
                klass = "good" if value >= 0.9 else ("bad" if value < 0.2 else "warn")
            cells.append(_cell(_pct(value), klass))
        rows.append(f'<tr class="{board["kind"]}">' + _cell(board["system"])
                    + "".join(cells) + "</tr>")
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(rows)}' \
           "</tbody></table></div>"


def _sensitivity_table(systems: list) -> str:
    dimensions = sorted({dimension for board in systems
                         for dimension in board["sensitivity"] if dimension != "worst"})
    head = "<tr><th>system</th>" + "".join(
        f"<th>{html.escape(name)}</th>" for name in dimensions) + "</tr>"
    rows = []
    for board in sorted(systems, key=lambda item: -item["strict"]["overall"]["rate"]):
        cells = []
        for dimension in dimensions:
            entry = board["sensitivity"].get(dimension)
            if not entry:
                cells.append(_cell("-"))
                continue
            spread = entry["spread_points"]
            klass = "bad" if spread >= 10 else ("warn" if spread >= 2 else None)
            cells.append(_cell(f"{spread:.1f} pt", klass))
        rows.append(f'<tr class="{board["kind"]}">' + _cell(board["system"])
                    + "".join(cells) + "</tr>")
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(rows)}' \
           "</tbody></table></div>"


# The systems the per-dialect detail is shown for. The degenerate baselines are left out of this
# one table only: `blank` and `ignore` score near zero under every dialect, so their rows would be
# a wall of zeroes obscuring the systems whose sensitivity is the point.
DETAIL_SYSTEMS = ("reference", "filler_keyword", "approximate")


def _dialect_tables(systems: list) -> str:
    """One small table per dimension, showing what each defensible reading actually scores.

    The spread alone hides which alternative caused it, and the answer is often a single extreme
    dialect rather than a general wobble. Publishing the whole row lets a reader disagree with the
    published choice and read off what their own choice would have scored.
    """
    shown = [board for board in systems
             if board["kind"] == "model" or board["system"] in DETAIL_SYSTEMS]
    shown.sort(key=lambda board: (board["kind"] != "model", -board["strict"]["overall"]["rate"]))
    dimensions = sorted({name for board in shown for name in board["sensitivity"]
                         if name != "worst"})
    blocks = []
    for dimension in dimensions:
        dialects, size = [], 0
        for board in shown:
            entry = board["sensitivity"].get(dimension)
            if entry:
                dialects = list(entry["by_dialect"])
                size = entry["n"]
                break
        if not dialects:
            continue
        head = "<tr><th>system</th>" + "".join(
            f"<th>{html.escape(name)}</th>" for name in dialects) + "<th>spread</th></tr>"
        rows = []
        for board in shown:
            entry = board["sensitivity"].get(dimension)
            if not entry:
                continue
            cells = []
            for dialect in dialects:
                value = entry["by_dialect"].get(dialect)
                klass = "good" if dialect == entry["published"] else None
                cells.append(_cell(_pct(value), klass))
            spread = entry["spread_points"]
            cells.append(_cell(f"{spread:.1f} pt",
                               "bad" if spread >= 10 else ("warn" if spread >= 2 else None)))
            rows.append(f'<tr class="{board["kind"]}">' + _cell(board["system"])
                        + "".join(cells) + "</tr>")
        blocks.append(
            f"<h3>{html.escape(dimension)} <span>over {size} items, published reading in "
            f"green</span></h3>"
            f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(rows)}'
            "</tbody></table></div>")
    return "".join(blocks)


def _fixture_caveats(systems: list) -> str:
    """Say, on the page, where a recorded answer ran out of generation budget.

    A leaderboard row that quietly averages in cut-off answers is publishing a property of the
    harness. Publishing the count next to the score lets a reader discount it, and separating the
    answers already past their target from the ones still in doubt says how much to discount.
    """
    rows = []
    for board in systems:
        notes = board.get("fixture") or {}
        if not notes.get("truncated"):
            continue
        share = notes.get("truncated_share", 0) * 100
        rows.append(
            f"<li><b>{html.escape(board['system'])}</b>: {notes['truncated']} of "
            f"{notes['rows']} answers ({share:.1f}%) stopped at the generation budget of "
            f"{max(notes.get('num_predict') or [0])} tokens, with "
            f"{notes.get('max_thinking_chars', 0)} characters of hidden reasoning at most. "
            f"{notes.get('truncated_undetermined', 0)} of those were still short of the target "
            f"when they stopped and are the only ones whose verdict finishing could have "
            f"changed; the rest were already past it.</li>")
    if not rows:
        return ("<p>No recorded answer stopped at the generation budget, so no row on this board "
                "is averaging in a sentence that was cut in half.</p>")
    return ("<p>Where a recording ran out of room, and how much of it is in doubt:</p><ul>"
            + "".join(rows) + "</ul>")


def _cards(report_data: dict) -> str:
    head = report_data["headline"]
    dataset = report_data["dataset"]
    swing = head["largest_sensitivity"]
    made = [
        (str(dataset["count"]), "prompts, each with a checkable count"),
        (_pct(head["filler_keyword_rate"]),
         "scored by <code>filler_keyword</code>, which says nothing at all"),
        (_pct(head["best_model_rate"]),
         f"best recorded model, {html.escape(str(head['best_model']))}"),
        (f"{swing['spread_points']:.1f} pt" if swing else "-",
         (f"largest swing from one defensible rule change "
          f"({html.escape(swing['dimension'])}, {html.escape(swing['system'])})")
         if swing else "no rule sensitivity measured"),
    ]
    return '<div class="cards">' + "".join(
        f"<div class=\"card\"><b>{value}</b><span>{label}</span></div>"
        for value, label in made) + "</div>"


def render(report_data: dict) -> str:
    dataset = report_data["dataset"]
    systems = report_data["systems"]
    rules_list = "".join(
        f"<li><code>{html.escape(dimension)}</code>: <code>{html.escape(dialect)}</code></li>"
        for dimension, dialect in sorted(dataset["published_rules"].items()))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>exactly: exact-count compliance</title>
<style>{STYLE}</style></head><body><main>
<h1>exactly</h1>
<p class="sub">{dataset['count']} prompts with a precisely checkable count constraint, graded
programmatically. Seed {dataset['seed']}, prompt set
<code>{html.escape(dataset['prompts_sha256'][:16])}</code>.</p>
{_cards(report_data)}
<h2>Leaderboard</h2>
<p>Compliance means all of it: the count is right under the published rule, the required keyword
is present, and for the unique-items family no two items say the same thing. Baselines are on the
same board as the models on purpose. <code>filler_keyword</code> emits the requested number of the
word <code>item</code> with the keyword dropped in, and whatever it scores is the ceiling on what
compliance means here.</p>
{_leaderboard_table(systems)}
<h3>Truncation</h3>
{_fixture_caveats(systems)}
<h2>By constraint family</h2>
<p>An upper bound is a different problem from an exact target. A system that simply writes less
than asked scores well on <code>sentences_at_most</code> and zero on <code>sentences_exact</code>,
so the families stay apart.</p>
{_family_table(systems, dataset['families'])}
<h2>Rule sensitivity</h2>
<p>Each cell is how far that system's compliance moves, in percentage points, when the counting
rule for that dimension is swapped for another defensible one and nothing else changes. It is
measured on the affected items only. A large number means the leaderboard is partly a measurement
of the splitter rather than of the model, which is worth more than the leaderboard.</p>
{_sensitivity_table(systems)}
<h2>Rule sensitivity in detail</h2>
<p>What each defensible reading actually scores, dimension by dimension. The largest single swing
in the whole report comes from the character rule, where counting only non-whitespace characters
takes the reference answers from full marks to nothing, because every one of them was composed to
hit a code point target with the spaces included. That is the honest shape of the problem. A
character constraint is close to meaningless without a stated definition, and a benchmark that
picks one silently is publishing its own choice as a property of the models.</p>
{_dialect_tables(systems)}
<h2>The published rules</h2>
<p>Every prompt carries, in the prompt, the exact rule its answer is graded under, because a model
cannot comply with a rule it was not told. The dialect in force for each dimension:</p>
<ul>{rules_list}</ul>
<footer>Generated from <code>results/leaderboard.json</code> by
<code>python3 -m exactly page</code>. Catalog task EVAL-040.</footer>
</main></body></html>
"""


def write(results_dir=None, docs_dir=None) -> pathlib.Path:
    docs_dir = DOCS if docs_dir is None else pathlib.Path(docs_dir)
    docs_dir.mkdir(exist_ok=True)
    path = docs_dir / "index.html"
    path.write_text(render(report.load(results_dir)), encoding="utf-8")
    return path
