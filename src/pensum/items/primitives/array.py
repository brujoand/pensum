"""An array of squares the pupil sizes by dragging its corner.

Multiplication as a rectangle rather than as a rule: 3 × 4 is three rows of
four, and the same rectangle turned is four rows of three. LK20 asks for exactly
that at 3. trinn (represent multiplication, use commutativity and
distributivity), and area at the same step is the same picture with a unit.

The pupil drags the corner handle and it snaps to the grid, or taps the square
the corner should reach, or uses the arrow keys on the handle. A split line,
when the item asks for one, cuts the array into two side by side: 6 × 7 as
6 × 5 and 6 × 2, which is distributivity drawn. It moves with Shift and the
arrow keys, the buttons, or a tap on the strip above the columns.

Graded on rows and columns (`accept: exact`), on either orientation
(`either_way`), or only on the number of squares (`product`, for "make an array
with 12 squares"), and on the split when one is declared.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label, Path
from pensum.items.primitives.base import (
    ActivityConfig,
    Board,
    Layer,
    Piece,
    Zone,
    say_keys,
)

MAX_SIDE = 10
CELL = 18.0
LEFT = 16.0
TOP = 26.0
# The strip above the columns where a tap puts the split line.
STRIP = 16.0
MARGIN = 12.0


class ArrayState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rows: int = Field(ge=1, le=MAX_SIDE)
    cols: int = Field(ge=1, le=MAX_SIDE)
    # The number of columns left of the split line. 0 is no split.
    split: int = Field(default=0, ge=0, le=MAX_SIDE - 1)


class ArrayActivity(ActivityConfig):
    """Make a `rows` × `cols` array, split after column `split` if given."""

    FALLBACK_KEY = "activity.array.ask"
    State = ArrayState

    kind: Literal["array"] = "array"
    rows: int = Field(ge=1, le=MAX_SIDE)
    cols: int = Field(ge=1, le=MAX_SIDE)
    accept: Literal["exact", "either_way", "product"] = "exact"
    split: int | None = Field(default=None, ge=1, le=MAX_SIDE - 1)

    @model_validator(mode="after")
    def _check(self) -> ArrayActivity:
        if self.split is not None:
            if self.split >= self.cols:
                raise ValueError(f"a split after column {self.split} is not inside {self.cols}")
            if self.accept != "exact":
                # A split is a statement about columns, and turning the array
                # round makes it a statement about rows.
                raise ValueError("a split array is graded exactly as asked")
        return self

    def initial(self) -> ArrayState:
        return ArrayState(rows=1, cols=1)

    def solution(self) -> ArrayState:
        return ArrayState(rows=self.rows, cols=self.cols, split=self.split or 0)

    def admits(self, state: ArrayState) -> bool:
        return state.split < state.cols

    def grade_state(self, state: ArrayState) -> bool:
        if self.split is not None and state.split != self.split:
            return False
        if self.accept == "product":
            return state.rows * state.cols == self.rows * self.cols
        if self.accept == "either_way":
            return sorted((state.rows, state.cols)) == sorted((self.rows, self.cols))
        return (state.rows, state.cols) == (self.rows, self.cols)

    def default_fallback(self) -> float:
        return float(self.rows * self.cols)

    def describe(self, state: ArrayState, locale: str) -> str:
        key = "activity.array.made_one" if state.rows == 1 else "activity.array.made"
        text = translate(locale, key, rows=state.rows, cols=state.cols)
        if state.split:
            text += ", " + translate(
                locale,
                "activity.array.made_split",
                left=state.split,
                right=state.cols - state.split,
            )
        return text

    def limits(self) -> dict[str, object]:
        return {
            "max": MAX_SIDE,
            "cell": CELL,
            "left": LEFT,
            "top": TOP,
            "split": self.split is not None,
        }

    def say(self, locale: str) -> dict[str, str]:
        return say_keys(
            locale,
            "activity.array.made",
            "activity.array.made_one",
            "activity.array.made_split",
        )

    def handle_at(self, state: ArrayState) -> tuple[float, float]:
        """Where the corner handle sits for a state, in board units."""
        return LEFT + state.cols * CELL, TOP + state.rows * CELL

    def board(self, state: ArrayState, locale: str) -> Board:
        size = MAX_SIDE * CELL
        paths: list[Path] = []
        # The whole grid, faint, so the pupil can see where the corner can go
        # before it goes there.
        for k in range(MAX_SIDE + 1):
            x, y = LEFT + k * CELL, TOP + k * CELL
            paths.append(Path(f"M{x:.2f},{TOP:.2f}L{x:.2f},{TOP + size:.2f}", "guide-faint"))
            paths.append(Path(f"M{LEFT:.2f},{y:.2f}L{LEFT + size:.2f},{y:.2f}", "guide-faint"))
        if state.split:
            x = LEFT + state.split * CELL
            paths.append(
                Path(f"M{x:.2f},{TOP - 6:.2f}L{x:.2f},{TOP + state.rows * CELL + 6:.2f}", "split")
            )

        pieces = [
            Piece(
                "cell",
                row * MAX_SIDE + col,
                "cell",
                LEFT + col * CELL,
                TOP + row * CELL,
                CELL,
                CELL,
                row < state.rows and col < state.cols,
                row=row,
                col=col,
            )
            for row in range(MAX_SIDE)
            for col in range(MAX_SIDE)
        ]
        zones = [Zone("grid", LEFT, TOP, size, size, role="zone grid")]
        if self.split is not None:
            zones.append(Zone("strip", LEFT, TOP - STRIP - 4, size, STRIP, role="zone strip"))
        caption = Label(
            LEFT + size / 2,
            TOP + size + MARGIN + 4,
            f"{state.rows} × {state.cols}",
            role="array-caption",
        )
        return Board(
            LEFT * 2 + size,
            TOP + size + MARGIN * 2 + 8,
            self.alt.get(locale),
            (Layer("base", tuple(paths), tuple(zones), tuple(pieces), (caption,)),),
        )
