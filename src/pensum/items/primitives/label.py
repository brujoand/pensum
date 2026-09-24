"""Labels put on numbered places on a picture.

Plant parts, the bones of a skeleton, the steps of the water cycle, the points
of a compass. The picture is what makes this a different question from a
match: the pupil has to find the part on the drawing, not only know the word.

**The picture is declared, not drawn.** An item names one of the diagrams
below (`diagram: water_cycle`) and which label goes on which of its places
(`slot: evaporation`); it never carries a path. That is the rule `figures.py`
gives for every figure -- a reviewer can check `slot: skull` against the
prompt, and nobody can check an SVG path -- and it is why the set is small. A
diagram is added here only when it can be drawn honestly from a few fixed
strokes; a map of real places, or an organ system drawn well enough to be
right, cannot, and is not offered.

Each place used is numbered on the drawing, and the labels go into a numbered
list beside it. There are no leader lines to follow, so the drawing stays
uncluttered and the list reads in order to a screen reader. The pupil drags a
label from the tray onto a number, taps the label and then the number, or picks
it from the number's own menu under the board, which is the keyboard path.

Graded on the label on each place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label, Path
from pensum.items.primitives.base import Board, Layer, Piece, Zone
from pensum.items.primitives.cards import ChoiceActivity, distinct, shuffled
from pensum.items.primitives.tiles import EMPTY, valid
from pensum.items.text import AuthoredText

NONE = EMPTY

DRAWING_W = 290.0
SLOT_X = 334.0
SLOT_W = 136.0
SLOT_H = 28.0
SLOT_GAP = 40.0
TRAY_GAP = 8.0
TRAY_PER_ROW = 3
MARKER_R = 9.0
MARGIN = 12.0


@dataclass(frozen=True)
class Diagram:
    """A picture with named places on it, in the order they are numbered."""

    height: float
    paths: tuple[Path, ...]
    anchors: tuple[tuple[str, float, float], ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _, _ in self.anchors)


def _circle(cx: float, cy: float, r: float) -> str:
    return f"M{cx - r:.1f},{cy:.1f} a{r:.1f},{r:.1f} 0 1 0 {2 * r:.1f},0 a{r:.1f},{r:.1f} 0 1 0 {-2 * r:.1f},0"


def _water_cycle() -> Diagram:
    rays = " ".join(
        f"M{40 + dx * 20:.1f},{40 + dy * 20:.1f} L{40 + dx * 27:.1f},{40 + dy * 27:.1f}"
        for dx, dy in (
            (0, -1),
            (0, 1),
            (-1, 0),
            (1, 0),
            (-0.7, -0.7),
            (0.7, -0.7),
            (-0.7, 0.7),
            (0.7, 0.7),
        )
    )
    return Diagram(
        240,
        (
            # The sea, bottom left, with a wave along its top.
            Path("M10,182 q15,-8 30,0 t30,0 t30,0 t30,0 L130,228 L10,228 Z", "fill"),
            # The sun.
            Path(_circle(40, 40, 14), "outline"),
            Path(rays, "outline"),
            # Water rising from the sea.
            Path("M55,172 L55,104 M80,172 L80,104", "guide"),
            Path("M49,114 L55,102 L61,114 M74,114 L80,102 L86,114", "outline"),
            # The cloud.
            Path(
                "M176,66 a12,12 0 0 1 4,-23 a16,16 0 0 1 30,-6 a13,13 0 0 1 24,10 a10,10 0 0 1 -2,19 Z",
                "outline",
            ),
            # Rain falling on the mountain.
            Path(
                "M196,76 l-5,12 M210,76 l-5,12 M224,76 l-5,12 M203,94 l-5,12 M217,94 l-5,12",
                "outline",
            ),
            # The mountain, and a river running down it to the sea.
            Path("M170,228 L240,122 L285,228 Z", "outline"),
            Path("M214,162 C198,182 178,190 130,200", "outline"),
        ),
        (
            ("condensation", 206, 50),
            ("precipitation", 238, 96),
            ("evaporation", 68, 138),
            ("runoff", 170, 186),
        ),
    )


def _skeleton() -> Diagram:
    ticks = " ".join(f"M141,{y} L149,{y}" for y in range(60, 146, 9))
    ribs = " ".join(f"M145,{y} q-30,2 -34,14 M145,{y} q30,2 34,14" for y in (74, 86, 98, 110))
    return Diagram(
        244,
        (
            Path(_circle(145, 32, 20), "outline"),
            Path("M145,52 L145,150", "outline"),
            Path(ticks, "outline"),
            Path("M105,64 L185,64", "outline"),
            Path(ribs, "outline"),
            Path("M118,148 L172,148 L160,168 L130,168 Z", "outline"),
            Path("M105,64 L96,120 L90,170 M185,64 L194,120 L200,170", "outline"),
            Path("M134,168 L128,206 L126,240 M156,168 L162,206 L164,240", "outline"),
        ),
        (
            ("skull", 145, 32),
            ("ribs", 118, 94),
            ("arm", 98, 104),
            ("spine", 145, 132),
            ("pelvis", 145, 158),
            ("thigh", 130, 188),
        ),
    )


def _compass() -> Diagram:
    cx, cy, arm, waist = 145, 124, 90, 9
    return Diagram(
        248,
        (
            Path(_circle(cx, cy, 44), "guide"),
            # The north arm is solid, as on a real compass rose; the others are
            # outlines. That is the one thing the picture gives away, and it is
            # what a pupil reading a map needs to know.
            Path(
                f"M{cx},{cy - arm} L{cx + waist},{cy - waist} L{cx - waist},{cy - waist} Z", "fill"
            ),
            Path(
                f"M{cx},{cy - arm} L{cx + waist},{cy - waist} L{cx + arm},{cy} "
                f"L{cx + waist},{cy + waist} L{cx},{cy + arm} L{cx - waist},{cy + waist} "
                f"L{cx - arm},{cy} L{cx - waist},{cy - waist} Z",
                "outline",
            ),
        ),
        (
            ("north", cx, cy - arm - 16),
            ("east", cx + arm + 16, cy),
            ("south", cx, cy + arm + 16),
            ("west", cx - arm - 16, cy),
        ),
    )


DIAGRAMS: dict[str, Diagram] = {
    "water_cycle": _water_cycle(),
    "skeleton": _skeleton(),
    "compass": _compass(),
}


class LabelCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: AuthoredText
    # The named place on the diagram this label belongs on.
    slot: str


class LabelState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Per numbered place, in number order: the label on it, or -1.
    slots: tuple[int, ...]


class LabelActivity(ChoiceActivity):
    """Put each of `labels` on its `slot` of `diagram`."""

    FALLBACK_KEY = "activity.label.ask"
    State = LabelState

    kind: Literal["label"] = "label"
    diagram: Literal["water_cycle", "skeleton", "compass"]
    labels: tuple[LabelCard, ...] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _check(self) -> LabelActivity:
        distinct([c.text for c in self.labels], "labels")
        names = DIAGRAMS[self.diagram].names
        used = [c.slot for c in self.labels]
        for slot in used:
            if slot not in names:
                raise ValueError(f"{self.diagram} has no place {slot!r}; it has {', '.join(names)}")
        if len(set(used)) != len(used):
            raise ValueError("two labels on one place")
        return self

    # --- places ------------------------------------------------------------

    def places(self) -> list[tuple[str, float, float]]:
        """The anchors in use, in the diagram's own order: numbered 1, 2, 3 ..."""
        used = {c.slot for c in self.labels}
        return [a for a in DIAGRAMS[self.diagram].anchors if a[0] in used]

    def answer(self) -> tuple[int, ...]:
        by_slot = {c.slot: j for j, c in enumerate(self.labels)}
        return tuple(by_slot[name] for name, _, _ in self.places())

    def tray_order(self) -> list[int]:
        return shuffled("|".join(c.text.nb for c in self.labels), len(self.labels))

    # --- rules -------------------------------------------------------------

    def initial(self) -> LabelState:
        return LabelState(slots=(NONE,) * len(self.labels))

    def solution(self) -> LabelState:
        return LabelState(slots=self.answer())

    def admits(self, state: LabelState) -> bool:
        # One label per place and one place per label: the language
        # primitives' slot rule, shared rather than written twice.
        return valid(state.slots, len(self.labels), len(self.labels))

    def grade_state(self, state: LabelState) -> bool:
        return state.slots == self.answer()

    def near_misses(self) -> list[LabelState]:
        """Two neighbouring places with their labels swapped."""
        right = list(self.answer())
        out = []
        for k in range(len(right) - 1):
            slots = list(right)
            slots[k], slots[k + 1] = slots[k + 1], slots[k]
            out.append(LabelState(slots=tuple(slots)))
        return out

    def describe(self, state: LabelState, locale: str) -> str:
        none = translate(locale, "activity.cards.none")
        return "; ".join(
            f"{k + 1}: {self.labels[j].text.get(locale) if j != NONE else none}"
            for k, j in enumerate(state.slots)
        )

    def limits(self) -> dict[str, int]:
        return {"cards": len(self.labels)}

    def say(self, locale: str) -> dict[str, object]:
        return {
            "none": translate(locale, "activity.cards.none"),
            "labels": [c.text.get(locale) for c in self.labels],
        }

    # --- drawing -----------------------------------------------------------

    def board(self, state: LabelState, locale: str) -> Board:
        diagram = DIAGRAMS[self.diagram]
        texts = [c.text.get(locale) for c in self.labels]
        places = self.places()
        paths = list(diagram.paths)
        labels: list[Label] = []
        zones: list[Zone] = []
        pieces: list[Piece] = []

        for k, (_, x, y) in enumerate(places):
            paths.append(Path(_circle(x, y, MARKER_R), "marker"))
            labels.append(Label(x, y, str(k + 1), size=11))
            sy = MARGIN + k * SLOT_GAP
            labels.append(Label(SLOT_X - 8, sy + SLOT_H / 2, f"{k + 1}", size=13, anchor="end"))
            zones.append(Zone(f"s{k}", SLOT_X, sy, SLOT_W, SLOT_H, index=k, role="zone slot"))
            for j, text in enumerate(texts):
                pieces.append(
                    Piece(
                        f"s{k}",
                        j,
                        "tile",
                        SLOT_X + 2,
                        sy + 2,
                        SLOT_W - 4,
                        SLOT_H - 4,
                        state.slots[k] == j,
                        label=text,
                    )
                )

        top = max(diagram.height, MARGIN + len(places) * SLOT_GAP) + MARGIN
        width = SLOT_X + SLOT_W + MARGIN
        placed = set(state.slots)
        rows = -(-len(texts) // TRAY_PER_ROW)
        tray_h = rows * SLOT_GAP + MARGIN
        # The labels not yet placed, in their own `tray` layer as the language
        # primitives draw theirs: part of the question, left out of feedback.
        tray_zone = Zone("tray", MARGIN, top, width - 2 * MARGIN, tray_h, role="zone tray")
        inner = width - 2 * MARGIN - 16
        tag_w = (inner - (TRAY_PER_ROW - 1) * TRAY_GAP) / TRAY_PER_ROW
        waiting: list[Piece] = []
        for at, j in enumerate(self.tray_order()):
            row, col = divmod(at, TRAY_PER_ROW)
            waiting.append(
                Piece(
                    "tray",
                    j,
                    "tile",
                    MARGIN + 8 + col * (tag_w + TRAY_GAP),
                    top + 8 + row * SLOT_GAP,
                    tag_w,
                    SLOT_H - 4,
                    j not in placed,
                    label=texts[j],
                )
            )
        return Board(
            width,
            top + tray_h + MARGIN,
            self.alt.get(locale),
            (
                Layer("base", tuple(paths), tuple(zones), tuple(pieces), tuple(labels)),
                Layer("tray", (), (tray_zone,), tuple(waiting)),
            ),
        )
