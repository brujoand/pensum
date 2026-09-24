"""A pan balance with weights and boxes: the equals sign as a relation.

`3 + 4 = ☐ + 5` is a balance with three and four on the left and a box and five
on the right. LK20 names the equals sign as a relation at 2. trinn (KM13242),
balance at 3., and solving equations with drawings and concrete materials at 5.
and 7.; the same board serves all of them (activities.md, "balance").

Two ways to meet the box, declared by `open_box`:

  * **Open** (the early years): the pupil fills the box with unit weights, and
    the beam tilts towards the heavier side and levels when the two sides weigh
    the same. That is what a balance does; it is the material answering, not a
    verdict, and nothing is graded until Check.
  * **Closed** (equations): the box is a closed bag that stands for a number.
    The balance is level because the task says it is. The pupil may take the
    same thing from both sides -- one weight, or one box -- which is solving an
    equation by the rule that keeps it balanced, and then says what the box is
    worth with the stepper.

Graded on the value of the box. With one unknown and a balanced start that is
the same thing as "balanced", and the validator makes sure every item has
exactly one whole-number answer. A state whose pans are not the declared pans
with the same amount taken from each side could not have come off this board,
and is wrong.
"""

from __future__ import annotations

from dataclasses import replace
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

MAX_WEIGHTS = 20
MAX_BOXES = 3
MAX_BOX_VALUE = 20

WIDTH = 300.0
PAN_W = 124.0
PLATE_Y = 118.0
BOX = 26.0
CUBE = 12.0
CUBE_GAP = 3.0
PIVOT = (150.0, 128.0)
# How far the beam turns, in degrees, and how far a pan drops, when one side is
# heavier. Small: the point is which way, not how much.
TILT = 6
DROP = 10


class Pan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    boxes: int = Field(default=0, ge=0, le=MAX_BOXES)
    weights: int = Field(default=0, ge=0, le=MAX_WEIGHTS)

    def weighs(self, box: int) -> int:
        return self.boxes * box + self.weights


class BalanceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left: Pan
    right: Pan
    box: int = Field(ge=0, le=MAX_BOX_VALUE)


class BalanceActivity(ActivityConfig):
    """What is in the box, if the two pans weigh the same?"""

    FALLBACK_KEY = "activity.balance.ask"
    State = BalanceState

    kind: Literal["balance"] = "balance"
    left: Pan
    right: Pan
    open_box: bool = False

    @model_validator(mode="after")
    def _check(self) -> BalanceActivity:
        if self.left.boxes + self.right.boxes == 0:
            raise ValueError("a balance with no box asks nothing")
        if self.left.boxes == self.right.boxes:
            raise ValueError("the same number of boxes on each side leaves the box unknowable")
        if self.box_value is None:
            raise ValueError("these pans balance for no whole number from 0 to 20")
        return self

    @property
    def box_value(self) -> int | None:
        """The one value that levels the balance, if it is a whole number."""
        boxes = self.left.boxes - self.right.boxes
        weights = self.right.weights - self.left.weights
        if boxes == 0 or weights % boxes:
            return None
        value = weights // boxes
        return value if 0 <= value <= MAX_BOX_VALUE else None

    def initial(self) -> BalanceState:
        return BalanceState(left=self.left, right=self.right, box=0)

    def solution(self) -> BalanceState:
        return BalanceState(left=self.left, right=self.right, box=self.box_value or 0)

    def admits(self, state: BalanceState) -> bool:
        # Only "the same from both sides" changes the pans, so what was taken
        # from the left must equal what was taken from the right.
        took_boxes = self.left.boxes - state.left.boxes
        took_weights = self.left.weights - state.left.weights
        return (
            took_boxes >= 0
            and took_weights >= 0
            and self.right.boxes - state.right.boxes == took_boxes
            and self.right.weights - state.right.weights == took_weights
        )

    def grade_state(self, state: BalanceState) -> bool:
        return state.box == self.box_value

    def default_fallback(self) -> float:
        return float(self.box_value or 0)

    def from_number(self, value: float) -> BalanceState | None:
        if not float(value).is_integer() or not 0 <= value <= MAX_BOX_VALUE:
            return None
        return BalanceState(left=self.left, right=self.right, box=int(value))

    def describe(self, state: BalanceState, locale: str) -> str:
        return translate(
            locale,
            "activity.balance.made",
            box=state.box,
            left=state.left.weighs(state.box),
            right=state.right.weighs(state.box),
        )

    def equation(self, state: BalanceState) -> str:
        return f"{side(state.left)} = {side(state.right)}"

    def limits(self) -> dict[str, object]:
        return {
            "open": self.open_box,
            "maxBox": MAX_BOX_VALUE,
            "pivot": list(PIVOT),
            "tilt": TILT,
            "drop": DROP,
        }

    def say(self, locale: str) -> dict[str, str]:
        return say_keys(locale, "activity.balance.status")

    def board(self, state: BalanceState, locale: str) -> Board:
        px, py = PIVOT
        # The stand and the beam do not move with the pans; the beam turns
        # about the pivot, which the page does by attribute.
        stand = Layer(
            "balance-stand",
            (
                Path(
                    f"M{px:.2f},{py:.2f}L{px - 18:.2f},{py + 34:.2f}L{px + 18:.2f},{py + 34:.2f}Z",
                    "outline",
                ),
            ),
        )
        tilt = _tilt(self, state)
        beam = Layer(
            "balance-beam",
            (Path(f"M{px - 92:.2f},{py:.2f}L{px + 92:.2f},{py:.2f}", "axis"),),
            transform=f"rotate({tilt * TILT} {px:.2f} {py:.2f})" if tilt else "",
        )
        layers = [stand, beam]
        for name, pan, x0, sign in (
            ("left", state.left, 14.0, -1),
            ("right", state.right, WIDTH - 14 - PAN_W, 1),
        ):
            layer = self._pan(name, pan, x0, state.box)
            if tilt:
                layer = replace(layer, transform=f"translate(0 {sign * tilt * DROP})")
            layers.append(layer)

        away_y = py + 44
        away = Layer(
            "base",
            zones=(Zone("away", px - 70, away_y, 140, 34, role="zone tray"),),
            labels=(Label(px, away_y + 17, translate(locale, "activity.balance.away"), size=11),),
        )
        layers.append(away)
        if self.open_box:
            # The spare weights an open box is filled from.
            layers.append(
                Layer(
                    "base",
                    zones=(Zone("supply", 14, away_y, 60, 34, role="zone tray"),),
                    pieces=(Piece("supply", 0, "cube", 14 + 24, away_y + 11, CUBE, CUBE),),
                )
            )
        return Board(WIDTH, away_y + 34 + 12, self.alt.get(locale), tuple(layers))

    def _pan(self, name: str, pan: Pan, x0: float, box: int) -> Layer:
        # A pan's pieces are drawn for everything the declared pan holds, so
        # that taking from both sides is hiding, never drawing.
        declared = self.left if name == "left" else self.right
        pieces: list[Piece] = []
        mark = str(box) if self.open_box else "?"
        for index in range(declared.boxes):
            pieces.append(
                Piece(
                    f"{name}-b",
                    index,
                    "box",
                    x0 + 4 + index * (BOX + 4),
                    PLATE_Y - BOX,
                    BOX,
                    BOX,
                    index < pan.boxes,
                    label=mark,
                )
            )
        base_y = PLATE_Y - (BOX + 4 if declared.boxes else 0)
        for index in range(declared.weights):
            row, col = divmod(index, 7)
            pieces.append(
                Piece(
                    f"{name}-w",
                    index,
                    "cube",
                    x0 + 4 + col * (CUBE + CUBE_GAP),
                    base_y - (row + 1) * (CUBE + CUBE_GAP),
                    CUBE,
                    CUBE,
                    index < pan.weights,
                )
            )
        plate = Path(f"M{x0:.2f},{PLATE_Y:.2f}L{x0 + PAN_W:.2f},{PLATE_Y:.2f}", "axis")
        hanger = Path(
            f"M{x0 + PAN_W / 2:.2f},{PLATE_Y:.2f}L{x0 + PAN_W / 2:.2f},{PIVOT[1]:.2f}", "outline"
        )
        return Layer(
            f"balance-pan balance-pan--{name}",
            (plate, hanger),
            (Zone(name, x0, 12, PAN_W, PLATE_Y - 12, role="zone pan"),),
            tuple(pieces),
        )


def side(pan: Pan) -> str:
    """One side of the balance as it is written: "☐ + ☐ + 3"."""
    terms = ["☐"] * pan.boxes + ([str(pan.weights)] if pan.weights else [])
    return " + ".join(terms) if terms else "0"


def _tilt(config: BalanceActivity, state: BalanceState) -> int:
    """-1 when the left side is heavier, 1 for the right, 0 when level.

    Only an open box moves the beam. A closed box stands for a number the pupil
    has not been told, and the premise of the task is that the pans balance.
    """
    if not config.open_box:
        return 0
    left, right = state.left.weighs(state.box), state.right.weighs(state.box)
    return (left < right) - (left > right)
