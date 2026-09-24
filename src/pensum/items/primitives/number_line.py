"""The number line, as the first primitive on the seam.

It existed before the seam did, and its declaration is the item's `figure` (a
`NumberLineFigure`) and `answer` rather than an `activity:` block. Moving it
onto the seam kept that YAML exactly as it was: this adapter reads the two
fields where they already are, and what moved is only *where the rules live* --
out of the branches in `schema.py` and `question.html` and into here.

Its feedback stays the plain "you answered / the answer is" pair: the line is
redrawn under it by the feedback partial, and a second drawing beside it would
be the same picture twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pensum.items.figures import NumberLineFigure, tick_index
from pensum.items.primitives import Primitive
from pensum.items.primitives.base import Comparison, number_text, parse_number

if TYPE_CHECKING:
    from pensum.items.schema import QuizItem


class NumberLinePrimitive(Primitive):
    def check(self, item: QuizItem) -> None:
        if not isinstance(item.figure, NumberLineFigure):
            raise ValueError(f"{item.id}: number_line items answer on a number_line figure")
        if item.answer is None:
            raise ValueError(f"{item.id}: number_line items need an answer")
        if item.tolerance:
            # The marker snaps to a tick, so there is no near miss to forgive:
            # an answer is the right tick or a different one.
            raise ValueError(f"{item.id}: a snapped answer has no tolerance")
        if tick_index(item.figure, item.answer) is None:
            raise ValueError(
                f"{item.id}: {item.answer} is not on a tick of "
                f"{item.figure.start}..{item.figure.end} step {item.figure.step}"
            )

    def grade(self, item: QuizItem, response: str) -> bool:
        value = parse_number(response)
        # Graded by which tick it is, not by how close it came: the marker
        # cannot rest between two, so a value that does is not an answer this
        # line could have produced. The isinstance is what `check` already
        # guarantees, narrowed again so grading does not depend on it.
        if value is None or item.answer is None or not isinstance(item.figure, NumberLineFigure):
            return False
        index = tick_index(item.figure, value)
        return index is not None and index == tick_index(item.figure, float(item.answer))

    def compare(self, item: QuizItem, response: str, locale: str) -> Comparison | None:
        return None

    def correct_text(self, item: QuizItem, locale: str) -> str:
        return number_text(float(item.answer)) if item.answer is not None else ""

    def response_text(self, item: QuizItem, response: str, locale: str) -> str:
        return response.strip()

    def board(self, item: QuizItem, locale: str) -> None:
        return None


NUMBER_LINE = NumberLinePrimitive(
    "number_line",
    "partials/number_line_input.html",
    "number-line.js",
    owns_figure=True,
)
