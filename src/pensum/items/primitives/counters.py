"""Counters on a mat, and optionally shared out into groups.

The first thing a child does with number: put things down and count them, then
push them into equal heaps. Counting, odd and even, grouping for
multiplication and sharing for division are all this one board, which is why it
is a primitive rather than four question types.

The pupil adds a counter by tapping the mat (or the box of spare counters, then
the mat), takes one away by moving it back to the box, and shares by moving
counters into group rings. Every move is also a button, which is the keyboard
path. The board snaps by construction: a counter is in a slot on the mat or in a
ring, never between.

Graded on the count, and, when the item declares groups, on the group sizes as
a multiset -- three rings of 4, 4 and 4 are right in any order, and nothing may
be left outside the rings.
"""

from __future__ import annotations

import math
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
    join_numbers,
    plural,
    say_keys,
)

MAX_ON_MAT = 30
MAX_GROUPS = 4
# How much room a ring leaves beyond the biggest group asked for. Enough that
# overfilling one is possible -- it is a real mistake to make and see -- without
# every ring being as big as the whole mat.
RING_SPARE = 4

SLOT = 22.0
RADIUS = 8.0
# A gap after the fifth counter in a row, so a row of ten reads as two fives.
FIVE_GAP = 8.0
MARGIN = 12.0
INSET = 6.0
PER_RING_ROW = 5


class CountersState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    loose: int = Field(ge=0)
    groups: tuple[int, ...] = ()


class CountersActivity(ActivityConfig):
    """Put `target` counters on the mat, or share them into `groups`."""

    FALLBACK_KEY = "activity.counters.ask_count"
    State = CountersState

    kind: Literal["counters"] = "counters"
    target: int = Field(ge=0, le=MAX_ON_MAT)
    # Counters already on the mat when the board opens. Sharing starts here:
    # twelve counters on the mat and three empty rings.
    start: int = Field(default=0, ge=0, le=MAX_ON_MAT)
    # The group sizes asked for. Empty means "just count".
    groups: tuple[int, ...] = Field(default=(), max_length=MAX_GROUPS)

    @model_validator(mode="after")
    def _check(self) -> CountersActivity:
        if self.groups:
            if len(self.groups) < 2:
                raise ValueError("one group is not a sharing; leave groups out to just count")
            if any(size < 1 for size in self.groups):
                raise ValueError("an empty group is not a group")
            if sum(self.groups) != self.target:
                raise ValueError(f"groups {self.groups} do not add up to {self.target}")
        return self

    # --- sizes ---------------------------------------------------------------

    @property
    def capacity(self) -> int:
        """How many counters the mat can hold: room to overshoot, in whole rows."""
        wanted = max(self.target, self.start) + 5
        return min(MAX_ON_MAT, max(10, math.ceil(wanted / 10) * 10))

    @property
    def ring_capacity(self) -> int:
        return min(self.capacity, max(self.groups, default=0) + RING_SPARE)

    def _equal_groups(self) -> bool:
        return bool(self.groups) and len(set(self.groups)) == 1

    def fallback_key(self) -> str:
        return "activity.counters.ask_each" if self._equal_groups() else self.FALLBACK_KEY

    # --- rules ---------------------------------------------------------------

    def initial(self) -> CountersState:
        return CountersState(loose=self.start, groups=(0,) * len(self.groups))

    def solution(self) -> CountersState:
        if self.groups:
            return CountersState(loose=0, groups=self.groups)
        return CountersState(loose=self.target)

    def admits(self, state: CountersState) -> bool:
        if len(state.groups) != len(self.groups):
            return False
        if state.loose > self.capacity or any(g > self.ring_capacity for g in state.groups):
            return False
        return state.loose + sum(state.groups) <= self.capacity

    def grade_state(self, state: CountersState) -> bool:
        if state.loose + sum(state.groups) != self.target:
            return False
        if not self.groups:
            return True
        return state.loose == 0 and sorted(state.groups) == sorted(self.groups)

    def default_fallback(self) -> float:
        return float(self.groups[0]) if self._equal_groups() else float(self.target)

    def from_number(self, value: float) -> CountersState | None:
        if not float(value).is_integer() or value < 0:
            return None
        n = int(value)
        if not self.groups:
            return CountersState(loose=n) if n <= self.capacity else None
        if (
            self._equal_groups()
            and n <= self.ring_capacity
            and n * len(self.groups) <= self.capacity
        ):
            return CountersState(loose=0, groups=(n,) * len(self.groups))
        return None

    def describe(self, state: CountersState, locale: str) -> str:
        count = state.loose + sum(state.groups)
        if not self.groups:
            return plural(locale, "activity.counters.made", count)
        text = translate(
            locale,
            "activity.counters.made_groups",
            count=count,
            sizes=join_numbers(state.groups, locale),
        )
        if state.loose:
            text += ", " + translate(locale, "activity.counters.made_loose", loose=state.loose)
        return text

    def limits(self) -> dict[str, int]:
        return {
            "capacity": self.capacity,
            "ring": self.ring_capacity,
            "groups": len(self.groups),
        }

    def say(self, locale: str) -> dict[str, str]:
        return say_keys(
            locale,
            "activity.counters.made",
            "activity.counters.made_one",
            "activity.counters.made_groups",
            "activity.counters.made_loose",
            "activity.and",
        )

    # --- drawing -------------------------------------------------------------

    def board(self, state: CountersState, locale: str) -> Board:
        capacity = self.capacity
        mat_rows = capacity // 10
        mat_w = 10 * SLOT + FIVE_GAP + 2 * INSET
        mat_h = mat_rows * SLOT + 2 * INSET
        left, top = MARGIN, MARGIN

        zones = [Zone("loose", left, top, mat_w, mat_h, role="zone mat")]
        pieces: list[Piece] = []
        for index in range(capacity):
            row, col = divmod(index, 10)
            x = left + INSET + col * SLOT + (FIVE_GAP if col >= 5 else 0)
            y = top + INSET + row * SLOT
            pieces.append(_counter("loose", index, x, y, index < state.loose))

        labels: list[Label] = []
        y = top + mat_h + MARGIN
        ring_rows = math.ceil(self.ring_capacity / PER_RING_ROW) if self.groups else 0
        ring_w = PER_RING_ROW * SLOT + 2 * INSET
        ring_h = ring_rows * SLOT + 2 * INSET
        for ring, size in enumerate(state.groups):
            line, place = divmod(ring, 2)
            x = left + place * (ring_w + MARGIN)
            ry = y + line * (ring_h + MARGIN + 14)
            labels.append(
                Label(
                    x + ring_w / 2,
                    ry + 6,
                    translate(locale, "activity.counters.group", n=ring + 1),
                    size=11,
                )
            )
            ry += 14
            zones.append(Zone(f"g{ring}", x, ry, ring_w, ring_h, role="zone ring"))
            for index in range(self.ring_capacity):
                row, col = divmod(index, PER_RING_ROW)
                pieces.append(
                    _counter(
                        f"g{ring}",
                        index,
                        x + INSET + col * SLOT,
                        ry + INSET + row * SLOT,
                        index < size,
                    )
                )
        if self.groups:
            lines = math.ceil(len(self.groups) / 2)
            y += lines * (ring_h + MARGIN + 14)

        # The box of spare counters: where new ones come from and old ones go.
        tray_w = 2 * SLOT + 2 * INSET
        zones.append(Zone("supply", left, y, tray_w, SLOT + 2 * INSET, role="zone tray"))
        pieces.append(_counter("supply", 0, left + INSET + SLOT / 2, y + INSET, True))
        labels.append(
            Label(
                left + tray_w + INSET,
                y + INSET + SLOT / 2,
                translate(locale, "activity.counters.supply"),
                size=11,
                anchor="start",
            )
        )
        height = y + SLOT + 2 * INSET + MARGIN
        width = left * 2 + max(mat_w, 2 * ring_w + MARGIN if self.groups else 0)
        paths: tuple[Path, ...] = ()
        return Board(
            width,
            height,
            self.alt.get(locale),
            (Layer("base", paths, tuple(zones), tuple(pieces), tuple(labels)),),
        )


def _counter(zone: str, index: int, x: float, y: float, shown: bool) -> Piece:
    inset = SLOT / 2 - RADIUS
    return Piece(zone, index, "counter", x + inset, y + inset, 2 * RADIUS, 2 * RADIUS, shown)
