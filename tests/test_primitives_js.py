"""The browser half of the hands-on primitives, and where it meets the server.

Each primitive's rules live twice: in JavaScript, deciding what a tap or a key
does to the board, and in Python, grading the state the board ends in and
drawing it. They are only safe together while they agree. A page that shows a
counter the server's drawing does not have, or writes a state the server
refuses, would mark a correct answer wrong and blame the child.

The checks that need only JavaScript are `tests/js/primitives.test.js`. This
runs it, then hands the real page functions the server's own states and boards
for every committed hands-on item, and asserts both sides say the same thing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pensum.items.loader import ItemBank

HARNESS = Path(__file__).parent / "js" / "primitives.test.js"
KINDS = ("counters", "ten_frame", "base_ten", "array", "balance")

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _node(script: str) -> str:
    # On stdin rather than `-e`: the cases for every committed item are more
    # than an argument list can carry.
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
    """Node is not a dependency, so the checks below skip without it --
    including, silently, if someone deletes the harness. This one does not."""
    assert HARNESS.is_file()


@needs_node
def test_the_primitives_harness() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _hands_on_items() -> list:
    bank = ItemBank.load()
    return [i for s in bank.item_sets for i in s.items if i.type in KINDS]


def _cases(locale: str = "nb") -> list[dict]:
    """For every committed hands-on item: its limits and templates, and the
    opening and the solved board as the server serialises and draws them."""
    cases = []
    for item in _hands_on_items():
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
        assert state is not None, case["id"]
        # Round-tripped: what the page would submit is what the server wrote,
        # up to the order of keys.
        assert state == case["dump"], case["id"]


@needs_node
def test_the_page_shows_exactly_the_pieces_the_server_draws() -> None:
    """The page never draws a piece; it shows and hides the ones the server
    placed. So for any state, which are shown has to be the same answer on
    both sides, piece by piece."""
    cases = _cases()
    shown = _run(
        cases,
        "const s = spec.parse(c.json, c.limits);"
        "return c.pieces.map((p) => !!spec.shown(s, p, c.limits));",
    )
    for case, page in zip(cases, shown, strict=True):
        server = [p["shown"] for p in case["pieces"]]
        assert page == server, case["id"]


@needs_node
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_live_status_says_what_the_feedback_says(locale: str) -> None:
    """The line the page reads out while the pupil builds, and the sentence
    the feedback prints afterwards, describe one state in the same words."""
    cases = [c for c in _cases(locale) if c["kind"] != "balance"]
    said = _run(cases, "return spec.describe(spec.parse(c.json, c.limits), c.say, c.limits);")
    for case, page in zip(cases, said, strict=True):
        # The ten-frame's feedback adds the fill pattern when it matters; the
        # live line reports only the count, which is its opening words.
        assert case["describe"].startswith(page), case["id"]


@needs_node
def test_a_board_built_by_the_buttons_is_graded_by_the_server() -> None:
    """Press buttons on the page's rules until the board is right, submit what
    the page would submit, and have the server grade it."""
    presses = {
        "KV1021-base_ten": (
            ("KM13232", "base_ten"),
            [{"type": "move", "from": "supply-tens", "to": "tens"}] * 3
            + [{"type": "move", "from": "supply-ones", "to": "ones"}] * 4,
        ),
        "KV1022-counters": (
            ("KM13246", "counters"),
            [{"type": "add", "zone": f"g{g}"} for g in (0, 1, 2) * 5],
        ),
        "KV1021-balance": (
            ("KM13242", "balance"),
            [{"type": "box", "by": 1}] * 2,
        ),
        "KV1022-array": (
            ("KM13247", "array"),
            [{"type": "rows", "by": 1}] * 2 + [{"type": "cols", "by": 1}] * 4,
        ),
        "KV1021-ten_frame": (("KM13234", "ten_frame"), [{"type": "add"}] * 3),
    }
    items = _hands_on_items()
    for name, ((goal, kind), actions) in presses.items():
        item = next(i for i in items if i.goal == goal and i.type == kind)
        activity = item.activity
        script = f"""
          const spec = require({json.dumps(str(HARNESS))})[{json.dumps(kind)}];
          const limits = {json.dumps(activity.limits())};
          let s = spec.parse({json.dumps(activity.serialise(activity.initial()))}, limits);
          for (const a of {json.dumps(actions)}) {{
            const next = spec.apply(s, a, limits);
            if (next === null) throw new Error("refused " + JSON.stringify(a));
            s = next;
          }}
          console.log(JSON.stringify(s));
        """
        submitted = _node(script).strip()
        assert item.is_correct(submitted), f"{name}: {submitted}"
