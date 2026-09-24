"""One or two ten-frames: two rows of five cells, a dot in some of them.

A ten-frame makes numbers to twenty visible as "five and a bit" and "ten and a
bit", which is what lets a child see 8 without counting it and see that 8 needs
2 more to make ten. The frame is the most-used manipulative in early number for
that reason.

The pupil taps an empty cell to put a dot in it, taps a dot to pick it up and
taps it again to take it away, or drags a dot to another cell. With a keyboard,
the arrow keys move a cursor over the cells and Space puts a dot down or takes
it away; the add and remove buttons do the same in reading order.

Graded on the count, and optionally on the fill pattern: `order: in_order`
asks for the conventional fill, top row left to right before the bottom row and
the first frame before the second, which is the pattern that makes "ten and
three" readable at a glance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Path
from pensum.items.primitives.base import (
    ActivityConfig,
    Board,
    Layer,
    Piece,
    Zone,
    plural,
    say_keys,
)

CELLS = 10
PER_ROW = 5
CELL = 30.0
RADIUS = 10.0
MARGIN = 12.0
FRAME_GAP = 14.0


class TenFrameState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Which cells hold a dot, per frame, numbered in reading order 0..9.
    frames: tuple[tuple[int, ...], ...]


class TenFrameActivity(ActivityConfig):
    """Show `target` dots on the frames."""

    FALLBACK_KEY = "activity.ten_frame.ask_count"
    State = TenFrameState

    kind: Literal["ten_frame"] = "ten_frame"
    frames: int = Field(default=1, ge=1, le=2)
    target: int = Field(ge=0, le=2 * CELLS)
    # Dots already there, filled in reading order: the "8" in "make 8 into 10".
    start: int = Field(default=0, ge=0, le=2 * CELLS)
    order: Literal["any", "in_order"] = "any"

    @model_validator(mode="after")
    def _check(self) -> TenFrameActivity:
        room = self.frames * CELLS
        if self.target > room or self.start > room:
            raise ValueError(f"{self.frames} frame(s) hold {room} dots at most")
        return self

    def _adding(self) -> bool:
        return 0 < self.start < self.target

    def fallback_key(self) -> str:
        return "activity.ten_frame.ask_add" if self._adding() else self.FALLBACK_KEY

    def _first(self, count: int) -> TenFrameState:
        """The first `count` cells in reading order, across the frames."""
        return TenFrameState(
            frames=tuple(
                tuple(range(max(0, min(CELLS, count - frame * CELLS))))
                for frame in range(self.frames)
            )
        )

    def initial(self) -> TenFrameState:
        return self._first(self.start)

    def solution(self) -> TenFrameState:
        return self._first(self.target)

    def admits(self, state: TenFrameState) -> bool:
        if len(state.frames) != self.frames:
            return False
        for cells in state.frames:
            if len(set(cells)) != len(cells) or any(not 0 <= c < CELLS for c in cells):
                return False
        return True

    def grade_state(self, state: TenFrameState) -> bool:
        if _count(state) != self.target:
            return False
        if self.order == "any":
            return True
        return _filled(state) == _filled(self.solution())

    def default_fallback(self) -> float:
        return float(self.target - self.start) if self._adding() else float(self.target)

    def from_number(self, value: float) -> TenFrameState | None:
        if not float(value).is_integer() or not 0 <= value <= self.frames * CELLS:
            return None
        if self._adding():
            # The typed number answered "how many more", so the board shows
            # the frame with that many added to what was there.
            total = self.start + int(value)
            return self._first(total) if total <= self.frames * CELLS else None
        return self._first(int(value))

    def describe(self, state: TenFrameState, locale: str) -> str:
        text = plural(locale, "activity.ten_frame.made", _count(state))
        if (
            self.order == "in_order"
            and _count(state) == self.target
            and _filled(state) != _filled(self.solution())
        ):
            text += ", " + translate(locale, "activity.ten_frame.out_of_order")
        return text

    def limits(self) -> dict[str, object]:
        return {"frames": self.frames, "cells": CELLS, "perRow": PER_ROW}

    def say(self, locale: str) -> dict[str, str]:
        return say_keys(
            locale,
            "activity.ten_frame.made",
            "activity.ten_frame.made_one",
            "activity.ten_frame.cell",
            "activity.ten_frame.full",
            "activity.ten_frame.empty",
        )

    def board(self, state: TenFrameState, locale: str) -> Board:
        width = 2 * MARGIN + PER_ROW * CELL
        paths: list[Path] = []
        zones: list[Zone] = []
        pieces: list[Piece] = []
        for frame in range(self.frames):
            top = MARGIN + frame * (2 * CELL + FRAME_GAP)
            filled = set(state.frames[frame]) if frame < len(state.frames) else set()
            # The frame: an outer box, a line between the rows, and a line
            # between each cell. Drawn as strokes, not as the zones, so the
            # frame is there without a script and the zones stay invisible.
            right, bottom = MARGIN + PER_ROW * CELL, top + 2 * CELL
            paths.append(
                Path(
                    f"M{MARGIN:.2f},{top:.2f}L{right:.2f},{top:.2f}L{right:.2f},{bottom:.2f}"
                    f"L{MARGIN:.2f},{bottom:.2f}Z",
                    "outline",
                )
            )
            paths.append(Path(f"M{MARGIN:.2f},{top + CELL:.2f}L{right:.2f},{top + CELL:.2f}"))
            for column in range(1, PER_ROW):
                x = MARGIN + column * CELL
                paths.append(Path(f"M{x:.2f},{top:.2f}L{x:.2f},{bottom:.2f}"))
            for cell in range(CELLS):
                row, column = divmod(cell, PER_ROW)
                x, y = MARGIN + column * CELL, top + row * CELL
                zones.append(Zone(f"f{frame}", x, y, CELL, CELL, index=cell, role="zone cell"))
                inset = CELL / 2 - RADIUS
                pieces.append(
                    Piece(
                        f"f{frame}",
                        cell,
                        "counter",
                        x + inset,
                        y + inset,
                        2 * RADIUS,
                        2 * RADIUS,
                        cell in filled,
                        row=row,
                        col=column,
                    )
                )
        height = MARGIN * 2 + self.frames * 2 * CELL + (self.frames - 1) * FRAME_GAP
        return Board(
            width,
            height,
            self.alt.get(locale),
            (Layer("base", tuple(paths), tuple(zones), tuple(pieces)),),
        )


def _count(state: TenFrameState) -> int:
    return sum(len(cells) for cells in state.frames)


def _filled(state: TenFrameState) -> tuple[frozenset[int], ...]:
    return tuple(frozenset(cells) for cells in state.frames)
