"""Base-ten blocks on a place-value mat: units, rods of ten, and flats of a hundred.

The swap is the lesson (activities.md). Ten units on the ones column can be
bundled into one rod, and a rod can be broken back into ten units. A pupil who
shows 52 - 17 by breaking a rod has done regrouping without the word being said,
and a pupil who builds 34 as two rods and fourteen units has shown they know
what a ten is worth even before they know to write it canonically.

The pupil adds a block by tapping its column (or picking it from the tray and
tapping the mat), takes one away by moving it back to the tray, and swaps by
tapping a block twice or dragging it onto the neighbouring column. Every move
is also a button. A block cannot land between columns: whatever column it is
dropped on, it goes to its own, and a rod dropped on the ones column is broken
into units there, which is what dropping it there means.

`accept` decides whether 2 tens and 14 ones counts as 34: `any_equivalent`
while exchange is what is being learned, `canonical` when the skill is writing
a number with at most nine in each place.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label
from pensum.items.primitives.base import (
    ActivityConfig,
    Board,
    Layer,
    Piece,
    Zone,
    plural,
    say_keys,
)

# Room to hold one ten more than a place can show, so any two-digit number can
# be built with a ten broken open, and no more.
MAX_ONES = 20
MAX_TENS = 20
MAX_HUNDREDS = 9

UNIT = 10.0
GAP = 5.0
# Not to scale. A flat drawn a hundred units big would push everything else off
# a phone screen; it is drawn with its ten-by-ten grid so what it is worth is
# still countable.
FLAT = 48.0
PAD = 8.0
MARGIN = 12.0
HEADER = 20.0
TRAY_H = FLAT + 2 * PAD

Place = Literal["hundreds", "tens", "ones"]


class BaseTenState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hundreds: int = Field(default=0, ge=0, le=MAX_HUNDREDS)
    tens: int = Field(default=0, ge=0, le=MAX_TENS)
    ones: int = Field(default=0, ge=0, le=MAX_ONES)

    @property
    def value(self) -> int:
        return 100 * self.hundreds + 10 * self.tens + self.ones


class BaseTenStart(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hundreds: int = Field(default=0, ge=0, le=MAX_HUNDREDS)
    tens: int = Field(default=0, ge=0, le=MAX_TENS)
    ones: int = Field(default=0, ge=0, le=MAX_ONES)


class BaseTenActivity(ActivityConfig):
    """Show `target` with blocks."""

    FALLBACK_KEY = "activity.base_ten.ask"
    State = BaseTenState

    kind: Literal["base_ten"] = "base_ten"
    target: int = Field(ge=0, le=999)
    # Hundreds are offered only when asked for: a 2. trinn mat with a column
    # nobody will use is one more thing to read.
    flats: bool = False
    accept: Literal["any_equivalent", "canonical"] = "any_equivalent"
    start: BaseTenStart = BaseTenStart()

    @model_validator(mode="after")
    def _check(self) -> BaseTenActivity:
        if not self.flats and self.target > 99:
            raise ValueError(f"{self.target} needs hundreds; set flats: true")
        if not self.flats and self.start.hundreds:
            raise ValueError("a start with hundreds needs flats: true")
        return self

    def places(self) -> tuple[Place, ...]:
        return ("hundreds", "tens", "ones") if self.flats else ("tens", "ones")

    def initial(self) -> BaseTenState:
        return BaseTenState(**self.start.model_dump())

    def solution(self) -> BaseTenState:
        hundreds, rest = divmod(self.target, 100)
        tens, ones = divmod(rest, 10)
        return BaseTenState(hundreds=hundreds, tens=tens, ones=ones)

    def admits(self, state: BaseTenState) -> bool:
        return self.flats or state.hundreds == 0

    def grade_state(self, state: BaseTenState) -> bool:
        if state.value != self.target:
            return False
        return self.accept == "any_equivalent" or (state.ones <= 9 and state.tens <= 9)

    def default_fallback(self) -> float:
        return float(self.target)

    def from_number(self, value: float) -> BaseTenState | None:
        limit = 999 if self.flats else 99
        if not float(value).is_integer() or not 0 <= value <= limit:
            return None
        hundreds, rest = divmod(int(value), 100)
        tens, ones = divmod(rest, 10)
        return BaseTenState(hundreds=hundreds, tens=tens, ones=ones)

    def describe(self, state: BaseTenState, locale: str) -> str:
        parts = []
        if self.flats:
            parts.append(plural(locale, "activity.base_ten.hundreds_count", state.hundreds))
        parts.append(plural(locale, "activity.base_ten.tens_count", state.tens))
        parts.append(plural(locale, "activity.base_ten.ones_count", state.ones))
        joined = ", ".join(parts[:-1]) + f" {translate(locale, 'activity.and')} {parts[-1]}"
        return translate(locale, "activity.base_ten.made", value=state.value, parts=joined)

    def limits(self) -> dict[str, int]:
        return {
            "hundreds": MAX_HUNDREDS if self.flats else 0,
            "tens": MAX_TENS,
            "ones": MAX_ONES,
        }

    def say(self, locale: str) -> dict[str, str]:
        return say_keys(
            locale,
            "activity.base_ten.made",
            "activity.base_ten.hundreds_count",
            "activity.base_ten.hundreds_count_one",
            "activity.base_ten.tens_count",
            "activity.base_ten.tens_count_one",
            "activity.base_ten.ones_count",
            "activity.base_ten.ones_count_one",
            "activity.and",
        )

    # --- drawing -------------------------------------------------------------

    def board(self, state: BaseTenState, locale: str) -> Board:
        columns = {
            "hundreds": (3 * FLAT + 2 * GAP + 2 * PAD, _flat_slots),
            "tens": (10 * UNIT + 9 * GAP + 2 * PAD, _rod_slots),
            "ones": (5 * UNIT + 4 * GAP + 2 * PAD, _unit_slots),
        }
        mat_h = 2 * 10 * UNIT + 2 * GAP + 2 * PAD
        top = MARGIN + HEADER
        x = MARGIN
        zones: list[Zone] = []
        pieces: list[Piece] = []
        labels: list[Label] = []
        counts = {"hundreds": state.hundreds, "tens": state.tens, "ones": state.ones}
        tray_top = top + mat_h + MARGIN

        for place in self.places():
            width, slots = columns[place]
            labels.append(
                Label(
                    x + width / 2,
                    MARGIN + HEADER / 2,
                    translate(locale, f"activity.base_ten.{place}"),
                )
            )
            zones.append(Zone(place, x, top, width, mat_h, role="zone column"))
            for index, (px, py) in enumerate(slots()):
                pieces.append(
                    _block(place, index, x + PAD + px, top + PAD + py, index < counts[place])
                )

            # The tray under each column: one block of that kind, always there,
            # to pick up or drag from. It is also where a block goes to be
            # taken away.
            zones.append(Zone(f"supply-{place}", x, tray_top, width, TRAY_H, role="zone tray"))
            pieces.append(_tray_block(place, x + width / 2, tray_top + TRAY_H / 2))
            x += width + MARGIN

        labels.append(
            Label(
                MARGIN,
                tray_top + TRAY_H + MARGIN,
                translate(locale, "activity.base_ten.tray"),
                size=11,
                anchor="start",
            )
        )
        height = tray_top + TRAY_H + MARGIN * 2
        return Board(
            x,
            height,
            self.alt.get(locale),
            (Layer("base", (), tuple(zones), tuple(pieces), tuple(labels)),),
        )


def _unit_slots() -> list[tuple[float, float]]:
    # Rows of five, with a gap after every two rows: each ten is a block of two
    # fives, the way a ten-frame shows it.
    out = []
    for index in range(MAX_ONES):
        row, column = divmod(index, 5)
        extra = GAP * 2 if row >= 2 else 0
        out.append((column * (UNIT + GAP), row * (UNIT + GAP) + extra))
    return out


def _rod_slots() -> list[tuple[float, float]]:
    return [
        ((index % 10) * (UNIT + GAP), (index // 10) * (10 * UNIT + 2 * GAP))
        for index in range(MAX_TENS)
    ]


def _flat_slots() -> list[tuple[float, float]]:
    return [
        ((index % 3) * (FLAT + GAP), (index // 3) * (FLAT + GAP)) for index in range(MAX_HUNDREDS)
    ]


def _block(place: str, index: int, x: float, y: float, shown: bool) -> Piece:
    if place == "ones":
        return Piece(place, index, "unit", x, y, UNIT, UNIT, shown)
    if place == "tens":
        # Ten segments, so a rod can be counted and is visibly ten units.
        detail = "".join(
            f"M{x:.2f},{y + k * UNIT:.2f}L{x + UNIT:.2f},{y + k * UNIT:.2f}" for k in range(1, 10)
        )
        return Piece(place, index, "rod", x, y, UNIT, 10 * UNIT, shown, detail)
    step = FLAT / 10
    detail = "".join(
        f"M{x + k * step:.2f},{y:.2f}L{x + k * step:.2f},{y + FLAT:.2f}"
        f"M{x:.2f},{y + k * step:.2f}L{x + FLAT:.2f},{y + k * step:.2f}"
        for k in range(1, 10)
    )
    return Piece(place, index, "flat", x, y, FLAT, FLAT, shown, detail)


def _tray_block(place: str, cx: float, cy: float) -> Piece:
    zone = f"supply-{place}"
    if place == "ones":
        return Piece(zone, 0, "unit", cx - UNIT / 2, cy - UNIT / 2, UNIT, UNIT)
    if place == "tens":
        # Lying down in the tray, so it fits under a column of standing rods.
        x, y = cx - 5 * UNIT, cy - UNIT / 2
        detail = "".join(
            f"M{x + k * UNIT:.2f},{y:.2f}L{x + k * UNIT:.2f},{y + UNIT:.2f}" for k in range(1, 10)
        )
        return Piece(zone, 0, "rod", x, y, 10 * UNIT, UNIT, True, detail)
    block = _block("hundreds", 0, cx - FLAT / 2, cy - FLAT / 2, True)
    return Piece(zone, 0, "flat", block.x, block.y, block.w, block.h, True, block.detail)
