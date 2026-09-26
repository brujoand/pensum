"""The browser half of the language primitives, and where it meets the server.

As `tests/test_primitives_js.py` does for the number primitives: the page's
rules and the server's are only safe together while they agree, so this runs
`tests/js/language_primitives.test.js` and then hands the real page functions
the server's own states and boards for every committed language item.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pensum.items.loader import ItemBank

HARNESS = Path(__file__).parent / "js" / "language_primitives.test.js"
KINDS = ("sound_boxes", "blend", "word_build", "sentence_build", "dialogue")

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
def test_the_language_primitives_harness() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _items() -> list:
    bank = ItemBank.load()
    return [i for s in bank.item_sets for i in s.items if i.type in KINDS]


def _cases(locale: str = "nb") -> list[dict]:
    """For every committed language item: its opening and its solved board, as
    the server serialises, describes and draws them."""
    cases = []
    for item in _items():
        activity = item.activity
        for name, state in (("initial", activity.initial()), ("solution", activity.solution())):
            board = activity.board(state, locale)
            cases.append(
                {
                    "id": f"{item.id}:{name}",
                    "kind": item.type,
                    "limits": activity.limits(),
                    "say": activity.say(locale),
                    "json": activity.serialise(state),
                    "dump": state.model_dump(mode="json"),
                    "describe": activity.describe(state, locale),
                    "pieces": [
                        {
                            "zone": p.zone,
                            "index": p.index,
                            "row": p.row,
                            "col": p.col,
                            "shown": p.shown,
                        }
                        for layer in board.layers
                        for p in layer.pieces
                        if not p.zone.startswith("supply")
                    ],
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
def test_the_page_shows_exactly_the_pieces_the_server_draws() -> None:
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


def _presses(item) -> list[dict]:
    """The button presses that answer a committed item, read off its solution:
    what a pupil using only the keyboard would do."""
    activity = item.activity
    solution = activity.solution()
    if item.type == "sound_boxes":
        adds = [{"type": "move", "from": "supply", "to": "counters"}] * solution.counters
        return adds + [{"type": "place", "zone": str(t)} for t in solution.slots if t != -1]
    if item.type == "blend":
        return [{"type": "join"}] * solution.joined + [{"type": "pick", "zone": solution.pick}]
    if item.type == "word_build":
        return [{"type": "place", "zone": str(t)} for t in solution.slots if t != -1]
    if item.type == "sentence_build":
        places = [{"type": "place", "zone": str(t)} for t in solution.slots if t != -1]
        # Flips are by double tap on the tile in its place.
        flips = [
            {"type": "act", "zone": f"s{solution.slots.index(t)}", "index": t}
            for t in solution.flipped
        ]
        return places + flips
    if item.type == "dialogue":
        steps = activity.walk(solution.picks)
        return [{"type": "pick", "zone": node, "by": pick} for node, pick in steps]
    raise AssertionError(item.type)


@needs_node
def test_a_board_built_by_the_buttons_is_graded_by_the_server() -> None:
    for item in _items():
        activity = item.activity
        script = f"""
          const spec = require({json.dumps(str(HARNESS))})[{json.dumps(item.type)}];
          const limits = {json.dumps(activity.limits())};
          let s = spec.parse({json.dumps(activity.serialise(activity.initial()))}, limits);
          for (const a of {json.dumps(_presses(item))}) {{
            const next = spec.apply(s, a, limits);
            if (next === null) throw new Error("refused " + JSON.stringify(a));
            s = next;
          }}
          console.log(JSON.stringify(s));
        """
        submitted = _node(script).strip()
        assert item.is_correct(submitted), f"{item.id}: {submitted}"
