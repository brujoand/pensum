"""The browser half of the simulations, and where it meets the server.

As `tests/test_language_primitives_js.py` does for the language primitives:
the page's rules and the server's are only safe together while they agree, so
this runs `tests/js/simulation_primitives.test.js` and then hands the real page
functions the server's own states, boards, draws and programs for every
committed simulation item.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pensum.items.loader import ItemBank
from pensum.items.primitives.step_code import StepCodeState, as_text

HARNESS = Path(__file__).parent / "js" / "simulation_primitives.test.js"
KINDS = ("trials", "step_code", "explore_sim")

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
def test_the_simulation_primitives_harness() -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _items() -> list:
    bank = ItemBank.load(include_unreviewed=True)
    return [i for s in bank.item_sets for i in s.items if i.type in KINDS]


def _states(item) -> list[tuple[str, object]]:
    """The states worth comparing: the opening, the solved one, and for trials
    one with trials run, so the bars and the tally are compared too."""
    activity = item.activity
    states = [("initial", activity.initial()), ("solution", activity.solution())]
    if item.type == "trials":
        states.append(
            (
                "run",
                activity.State(
                    prediction=activity.right(),
                    seed=987654,
                    done=110,
                    tally=activity.simulate(987654, 110),
                ),
            )
        )
    return states


def _cases(locale: str = "nb") -> list[dict]:
    cases = []
    for item in _items():
        activity = item.activity
        for name, state in _states(item):
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


@needs_node
def test_the_page_draws_what_the_server_replays() -> None:
    for item in _items():
        if item.type != "trials":
            continue
        activity = item.activity
        seeds = [1, 2, 77, 2**31 - 1, 123456789]
        script = f"""
          const spec = require({json.dumps(str(HARNESS))}).trials;
          const limits = {json.dumps(activity.limits())};
          console.log(JSON.stringify({json.dumps(seeds)}.map((s) => spec.simulate(s, 1000, limits))));
        """
        page = json.loads(_node(script))
        assert page == [list(activity.simulate(s, 1000)) for s in seeds], item.id


@needs_node
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_page_runs_and_writes_a_program_the_way_the_server_does(locale: str) -> None:
    for item in _items():
        if item.type != "step_code":
            continue
        activity = item.activity
        programs = [activity.solution_program, activity.begin, *activity.near_misses()]
        dumps = [StepCodeState(program=p).model_dump(mode="json")["program"] for p in programs]
        script = f"""
          const spec = require({json.dumps(str(HARNESS))}).step_code;
          const limits = {json.dumps(activity.limits())};
          const say = {json.dumps(activity.say(locale))};
          const out = {json.dumps(dumps)}.map((p) => {{
            const run = spec.trace(p, limits);
            return [run.poses, run.outcome, spec.text(p, say)];
          }});
          console.log(JSON.stringify(out));
        """
        page = json.loads(_node(script))
        for program, (poses, outcome, text) in zip(programs, page, strict=True):
            run = activity.trace(program)
            assert [tuple(p) for p in poses] == list(run.poses), item.id
            assert outcome == run.outcome, item.id
            assert text == as_text(program, locale), item.id


def _presses(item) -> list[dict]:
    """The button presses that answer a committed item, read off its solution:
    what a pupil using only the keyboard would do."""
    activity = item.activity
    if item.type == "trials":
        return [
            {"type": "predict", "zone": activity.right()},
            {"type": "run", "by": 10},
            {"type": "run", "by": 100},
        ]
    if item.type == "explore_sim":
        other = 1 if activity.start == 0 else 0
        return [
            {"type": "predict", "zone": activity.predict.choices[-1].id},
            {"type": "slide", "by": other},
            {"type": "explain", "zone": activity.explain.answer},
        ]
    presses: list[dict] = []
    # Clear what the board opens with -- each press removes the tile or the
    # whole block before the marker -- then build the solution tile by tile.
    presses += [{"type": "remove"}] * len(activity.begin)

    def build(program) -> None:
        for command in program:
            if isinstance(command, str):
                presses.append({"type": "add", "zone": command})
                continue
            data = command.model_dump(mode="json")
            if "repeat" in data:
                presses.append({"type": "add", "zone": "repeat", "by": data["repeat"]})
                build(command.do)
            else:
                presses.append({"type": "add", "zone": "if_wall"})
                build(command.if_wall)
            presses.append({"type": "out"})

    build(activity.solution_program)
    return presses


@needs_node
def test_a_board_built_by_the_buttons_is_graded_by_the_server() -> None:
    for item in _items():
        activity = item.activity
        script = f"""
          const spec = require({json.dumps(str(HARNESS))})[{json.dumps(item.type)}];
          const limits = {json.dumps(activity.limits())};
          let s = spec.parse({json.dumps(activity.serialise(activity.opening()))}, limits);
          for (const a of {json.dumps(_presses(item))}) {{
            const next = spec.apply(s, a, limits);
            if (next === null) throw new Error("refused " + JSON.stringify(a));
            s = next;
          }}
          console.log(JSON.stringify(s));
        """
        submitted = _node(script).strip()
        assert item.is_correct(submitted), f"{item.id}: {submitted}"
