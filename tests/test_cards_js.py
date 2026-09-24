"""The browser half of the card primitives, and where it meets the server.

As `tests/test_primitives_js.py` does for the number boards: the checks that
need only JavaScript are in `tests/js/cards.test.js`, and this runs it, then
hands the real page functions the server's own states and boards for every
committed card item and asserts both sides say the same thing. A page that
showed a card where the server's board has none, or wrote a state the server
refuses, would mark a right answer wrong.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pensum.items.loader import ItemBank
from pensum.items.primitives.cards import CardBoard

HARNESS = Path(__file__).parent / "js" / "cards.test.js"
KINDS = ("sort", "sequence", "match", "label", "highlight")

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _node(script: str) -> str:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", "-"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_the_harness_is_reachable() -> None:
    assert HARNESS.is_file()


@needs_node
def test_the_cards_harness() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _card_items() -> list:
    bank = ItemBank.load(include_unreviewed=True)
    return [i for s in bank.item_sets for i in s.items if i.type in KINDS]


def _pieces(board: object) -> list[dict]:
    """Every card or label the page could show or hide, and whether the
    server's board shows it. The always-there columns are left out: the page
    never hides them."""
    if isinstance(board, CardBoard):
        cards = [c for place in board.places for c in place.cards]
    else:
        cards = [p for layer in board.layers for p in layer.pieces]
    return [
        {"zone": c.zone, "index": c.index, "shown": c.shown}
        for c in cards
        if not c.zone.startswith("supply")
    ]


def _cases(locale: str = "nb") -> list[dict]:
    """For every committed card item: its limits and templates, and every
    state the server itself offers -- the opening, the solution and each
    near miss the no-script choice shows."""
    cases = []
    for item in _card_items():
        activity = item.activity
        states = [("initial", activity.initial()), ("solution", activity.solution())]
        states += [(f"miss{n}", s) for n, s in enumerate(activity.near_misses()[:3])]
        for name, state in states:
            if activity.read(activity.serialise(state)) is None:
                continue
            cases.append(
                {
                    "id": f"{item.id}:{name}",
                    "kind": item.type,
                    "limits": activity.limits(),
                    "say": activity.say(locale),
                    "json": activity.serialise(state),
                    "dump": state.model_dump(mode="json"),
                    "describe": activity.describe(state, locale),
                    "pieces": _pieces(activity.board(state, locale)),
                }
            )
    return cases


def _run(cases: list[dict], body: str) -> list:
    script = f"""
      const specs = require({json.dumps(str(HARNESS))});
      const cases = {json.dumps(cases)};
      const out = cases.map((c) => {{
        const spec = specs[c.kind];
        {body}
      }});
      console.log(JSON.stringify(out));
    """
    return json.loads(_node(script))


@needs_node
def test_the_page_reads_every_state_the_server_writes() -> None:
    cases = _cases()
    assert {c["kind"] for c in cases} == set(KINDS)
    parsed = _run(cases, "return spec.parse(c.json, c.limits);")
    for case, state in zip(cases, parsed, strict=True):
        assert state == case["dump"], case["id"]


@needs_node
def test_the_page_shows_exactly_the_cards_the_server_draws() -> None:
    cases = _cases()
    shown = _run(
        cases,
        "const s = spec.parse(c.json, c.limits);"
        "return c.pieces.map((p) => !!spec.shown(s, p, c.limits));",
    )
    for case, page in zip(cases, shown, strict=True):
        assert page == [p["shown"] for p in case["pieces"]], case["id"]


@needs_node
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_live_status_says_what_the_feedback_says(locale: str) -> None:
    cases = _cases(locale)
    said = _run(cases, "return spec.describe(spec.parse(c.json, c.limits), c.say, c.limits);")
    for case, page in zip(cases, said, strict=True):
        assert page == case["describe"], case["id"]


@needs_node
def test_a_board_built_by_the_page_is_graded_by_the_server() -> None:
    """Build each committed item's answer with the page's own moves -- the
    menus for the boards that have them, the buttons for a sequence, the taps
    for a highlight -- submit what the page would submit, and have the server
    grade it."""
    for item in _card_items():
        activity = item.activity
        answer = activity.solution()
        if item.type == "sort":
            actions = [
                {"type": "place", "index": i, "zone": f"r{p}"} for i, p in enumerate(answer.place)
            ]
        elif item.type == "match":
            actions = [{"type": "pair", "row": i, "card": j} for i, j in enumerate(answer.pairs)]
        elif item.type == "label":
            actions = [{"type": "place", "slot": k, "card": j} for k, j in enumerate(answer.slots)]
        elif item.type == "highlight":
            actions = [{"type": "toggle", "index": t} for t in answer.marked]
        else:
            # Bubble sort with the up buttons: what a keyboard user would do.
            order = list(activity.initial().order)
            actions = []
            done = False
            while not done:
                done = True
                for at in range(1, len(order)):
                    if order[at] < order[at - 1]:
                        order[at], order[at - 1] = order[at - 1], order[at]
                        actions.append({"type": "up", "zone": f"p{at}"})
                        done = False
        script = f"""
          const spec = require({json.dumps(str(HARNESS))})[{json.dumps(item.type)}];
          const limits = {json.dumps(activity.limits())};
          let s = spec.parse({json.dumps(activity.serialise(activity.initial()))}, limits);
          for (const a of {json.dumps(actions)}) {{
            const next = spec.apply(s, a, limits);
            if (next !== null) s = next;
          }}
          console.log(JSON.stringify(s));
        """
        submitted = _node(script).strip()
        assert item.is_correct(submitted), f"{item.id}: {submitted}"
