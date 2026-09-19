"""The browser half of the number-line question.

`number-line.js` decides which tick a finger landed on, and the server decides
whether that tick is the answer. Those are two implementations of one piece of
arithmetic, in two languages, and the item is only safe to score while they
agree: the server rejects any value that is not on a tick, so a page that
snapped differently would mark a correct drag wrong and blame the child.

The checks that only need JavaScript live in `tests/js/number_line_snap.test.js`.
This shells out to node and reports what it said, then adds the check that
cannot live on either side alone: node and Python are handed the same pointer
positions and have to name the same tick.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pensum.items.figures import (
    NumberLineFigure,
    line_geometry,
    line_x,
    tick_count,
    tick_index,
)
from pensum.items.text import AuthoredText

HARNESS = Path(__file__).parent / "js" / "number_line_snap.test.js"
SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "pensum" / "web" / "static" / "number-line.js"
)

# The line the converted item uses: 0 to 50 in fives, so the answer sits on an
# unlabelled tick between two labelled ones.
FIGURE = NumberLineFigure(
    alt=AuthoredText(nb="En tallinje", en="A number line"), start=0, end=50, step=5
)


def _node() -> str:
    return shutil.which("node") or "node"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_snapping_harness() -> None:
    result = subprocess.run(  # noqa: S603
        [_node(), str(HARNESS)],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_the_harness_is_reachable() -> None:
    """Node is not a dependency of this project, so the check above skips where
    it is missing -- including, silently, if someone deletes the harness. This
    one does not skip."""
    assert HARNESS.is_file()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_and_the_server_snap_to_the_same_tick() -> None:
    """The arithmetic that has to be the same in two languages.

    Swept across the whole line rather than spot-checked, because the failure
    this guards against is an off-by-half-a-tick that only shows up near the
    boundaries between them -- exactly where a child aiming at a number lets go.
    """
    geometry = line_geometry(FIGURE)
    left, right = geometry["left"], geometry["right"]

    # 199 samples across a ten-tick line, so no sample lands exactly halfway
    # between two ticks. A tie there is not a disagreement worth failing on: the
    # two sides reach the boundary by different arithmetic, and a pointer that
    # precise is not something a child produces. The harness pins the rounding
    # either side of a boundary on the page's own terms.
    span = right - left
    positions = [left + span * i / 198 for i in range(199)]
    # And well past both ends: a finger that slid off the line still has to be
    # given the end tick by both sides.
    positions += [left - 500, right + 500]

    # The harness exports the functions it pulled out of the shipped file, so
    # this runs the real snapping rather than a transcription of it.
    script = f"""
      const {{ tickAt, valueAt }} = require({json.dumps(str(HARNESS))});
      const positions = {json.dumps(positions)};
      const last = {round((FIGURE.end - FIGURE.start) / FIGURE.step)};
      console.log(JSON.stringify(positions.map(
        (x) => valueAt(tickAt(x, {left}, {right}, last), {FIGURE.start}, {FIGURE.step})
      )));
    """
    result = subprocess.run(  # noqa: S603
        [_node(), "-e", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=HARNESS.parents[2],
    )
    assert result.returncode == 0, result.stdout + result.stderr

    from_page = json.loads(result.stdout)

    # The tick whose drawn position is nearest the pointer, found by measuring
    # against `line_x` -- the same function that put the ticks on the page. The
    # page reaches this by inverting the mapping instead of searching it, and
    # the two have to name the same tick.
    ticks = [FIGURE.start + i * FIGURE.step for i in range(tick_count(FIGURE))]
    from_server = [min(ticks, key=lambda v, x=x: abs(line_x(FIGURE, v) - x)) for x in positions]
    assert from_page == from_server

    # And what the page produces is always something the server will grade: a
    # value off a tick is refused, so a disagreement here is a wrong answer for
    # a right drag.
    assert all(tick_index(FIGURE, value) is not None for value in from_page)


def _render(item) -> str:
    """The question partial on its own, with the little context it needs."""
    from pensum.i18n import translate
    from pensum.web.rendering import templates

    return templates.get_template("partials/question.html").render(
        item=item,
        locale="nb",
        t=lambda key, **kwargs: translate("nb", key, **kwargs),
        answer_url="/nb/quiz/x/answer",
        result_url="/nb/quiz/x/result",
        progress="1",
        drafts_visible=False,
    )


def test_the_page_offers_both_roads_to_the_answer() -> None:
    """Dragging is the question; typing is the same answer for a pupil who
    cannot place a pointer, and WCAG 2.5.7 requires it to be there."""
    from pensum.items.schema import QuizItem

    item = QuizItem(
        id="KM1-l",
        goal="KM1",
        type="number_line",
        difficulty=1,
        prompt=AuthoredText(nb="Sett merket", en="Place the marker"),
        explanation=AuthoredText(nb="Slik", en="Like so"),
        figure=FIGURE,
        answer=35,
    )
    html = _render(item)

    assert "data-number-line" in html
    assert 'name="response"' in html
    # One picture, not two: a number_line item draws its own, so the generic
    # figure block above the answers has to stand down for it.
    assert html.count("<svg") == 1
