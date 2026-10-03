"""Pictures for questions that describe something you are supposed to see.

A lot of matematikk is written as a sentence about an object: a triangle with
three sides, a rectangle covered by twelve squares, a pizza cut in four with one
piece gone. A seven-year-old who cannot yet read fluently is then being tested
on reading rather than on counting, and a ten-year-old asked what happens to the
area when the side doubles has to hold two squares in their head before they can
start. Drawing the thing removes a step that was never the point of the
question.

**A figure is declared, not drawn.** An item names a *kind* -- a shape, a row of
counters, an array, a fraction, a number line, a box -- and the parameters that make
this one different from the next. Nothing here accepts an SVG path or a markup
fragment from the data. That is deliberate and it is the same argument the
alphabet makes in reverse: a letterform is authored as a path because a path is
the letter, whereas a figure is authored as a parameter because nobody can
review `M20,20L180,180` against the sentence it is supposed to illustrate. A
declared figure is checkable by eye in the YAML and by assertion in a test --
`parts: 4, shaded: 1` is either 1/4 or it is a typo somebody can see.

**It renders server-side, to plain SVG, with no script.** The exercise is a page
a child reads; a picture that needs JavaScript to exist is a picture that is
sometimes missing. `draw()` turns a figure into three flat lists -- paths, dots
and labels -- and the template loops over them, so the geometry is testable
without a browser and the template stays too dumb to be wrong.

**Every figure carries its own alt text, in both locales.** A picture that
replaces a sentence has to say the same thing to a screen reader, and no
generator can write that sentence from the parameters: only the author knows
which part of the drawing the question turns on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.items.text import AuthoredText

# The box every figure is drawn in, in its own units. Not a pixel size -- the
# page scales it to whatever the column allows -- but the units every constant
# below is in.
VIEW = 200.0

# Room for a label to sit outside the shape it belongs to without being clipped.
# A side label on a triangle hangs off the edge by construction.
PAD = 26.0

# Text sizes, in view units. Two rather than one because a side label and a
# number-line tick are read at different distances from the thing they name.
LABEL_SIZE = 13.0
TICK_SIZE = 11.0

# How far a side label sits from its side, and how wide a character of it is
# taken to be. The width is an estimate, since the renderer never measures
# text: sans-serif digits average a little over half their height, and
# overestimating costs a slightly smaller shape rather than a clipped label.
SIDE_GAP = LABEL_SIZE * 0.9
CHAR_WIDTH = 0.62
# The least space between two labels side by side, so they read as two.
LABEL_GAP = LABEL_SIZE * 0.5

# The narrowest a shape is drawn across, so labels beside its left and right
# sides can never squeeze it to nothing. 60 is what the box keeps too, and it
# leaves room for a label of 7 characters on each side ("12,5 cm").
MIN_SHAPE_WIDTH = 60.0
MAX_SIDE_MARGIN = (VIEW - MIN_SHAPE_WIDTH) / 2
MAX_BESIDE_LABEL = int((MAX_SIDE_MARGIN - SIDE_GAP) / (LABEL_SIZE * CHAR_WIDTH))

# A figure nobody could take in at a glance is not helping. These caps are
# about legibility at the size a phone renders a quiz question, not about
# arithmetic: forty counters is already a wall of dots.
MAX_COUNTERS = 40
MAX_ARRAY_SIDE = 12
MAX_PARTS = 12
MAX_ROWS = 4
MAX_TICKS = 41

# How big a right-angle mark is, relative to the shorter of the two sides that
# meet there. Proportional rather than fixed so it does not swallow a small
# corner or vanish in a large one.
RIGHT_ANGLE_FRACTION = 0.16

# How much room a number line leaves above itself for jump arcs. Only
# claimed when there are jumps to draw -- see `_draw_number_line`.
JUMP_BAND = 46.0

# Named shapes and their vertices in a unit box. Every one is listed clockwise
# starting from the topmost vertex -- the leftmost of them where two are level
# -- so "side 0" is always the one leaving the top of the figure, and an author
# labelling sides can predict where a label lands without rendering it first.
#
# The proportions are conventional textbook ones rather than measured. A
# rectangle labelled 3 cm by 4 cm is not drawn to scale, and no figure here
# claims to be -- `array` is the kind that is, because a rectangle made of
# squares can be counted.
_UNIT_SHAPES: dict[str, tuple[tuple[float, float], ...]] = {
    "triangle": ((0.5, 0.0), (1.0, 1.0), (0.0, 1.0)),
    "right_triangle": ((0.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    "square": ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    "rectangle": ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    "parallelogram": ((0.25, 0.0), (1.0, 0.0), (0.75, 1.0), (0.0, 1.0)),
    "rhombus": ((0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)),
    "trapezoid": ((0.25, 0.0), (0.75, 0.0), (1.0, 1.0), (0.0, 1.0)),
}

# The regular polygons, by vertex count. Generated rather than tabulated: a
# hand-typed heptagon is a source of very quiet bugs.
_REGULAR = {"pentagon": 5, "hexagon": 6, "octagon": 8}

ShapeName = Literal[
    "triangle",
    "right_triangle",
    "square",
    "rectangle",
    "parallelogram",
    "rhombus",
    "trapezoid",
    "pentagon",
    "hexagon",
    "octagon",
    "circle",
]

# Which shapes it is meaningful to squash. A square that is not square, or a
# regular hexagon that is not regular, is a different shape wearing the name.
_STRETCHABLE = {"rectangle", "right_triangle", "parallelogram", "trapezoid", "triangle"}

# Which shapes `divide_at` can split with vertical lines into smaller ones of
# the same kind. A divided triangle is a different picture.
_DIVISIBLE = {"rectangle", "square"}

# How wide each shape is drawn relative to its height, unless an author says
# otherwise. Per shape rather than one number for all of them, because the unit
# boxes above describe *which corner goes where* and say nothing about
# proportion: drawn in a single box, a square comes out a rectangle and a
# rhombus comes out a kite. The regular polygons are excluded because their own
# geometry settles it -- see `_natural_ratio`.
_NATURAL_RATIO: dict[str, float] = {
    "triangle": 1.25,
    "right_triangle": 1.25,
    "square": 1.0,
    "rectangle": 1.6,
    "parallelogram": 1.5,
    "rhombus": 1.0,
    "trapezoid": 1.4,
}

# Which vertex an altitude is dropped from, for the shapes an author can ask for
# a height on. Only the triangle: a parallelogram has two candidate bases, a
# hexagon has none, and a right triangle's height *is* one of its sides -- a
# dashed line drawn along a side the figure already has reads as a fault rather
# than as a measurement.
_APEX: dict[str, int] = {"triangle": 0}


def _vertex_count(shape: ShapeName) -> int:
    if shape == "circle":
        return 0
    if shape in _REGULAR:
        return _REGULAR[shape]
    return len(_UNIT_SHAPES[shape])


@dataclass(frozen=True)
class Path:
    """One stroke of the drawing, as SVG path data plus what it is for.

    `role` becomes a class name, so the stylesheet decides what an outline
    versus a fill versus a dashed guide looks like. Colour and stroke width are
    never authored: a figure that renders differently from its neighbours reads
    as a different kind of statement.
    """

    d: str
    role: str = "outline"


@dataclass(frozen=True)
class Dot:
    cx: float
    cy: float
    r: float
    role: str = "mark"


@dataclass(frozen=True)
class Label:
    x: float
    y: float
    text: str
    role: str = "label"
    size: float = LABEL_SIZE
    # SVG's own values, so the template can set the attribute directly.
    anchor: str = "middle"
    baseline: str = "middle"


@dataclass(frozen=True)
class Drawing:
    """A figure resolved to primitives, ready for a template that cannot think."""

    width: float
    height: float
    alt: str
    paths: tuple[Path, ...] = ()
    dots: tuple[Dot, ...] = ()
    labels: tuple[Label, ...] = ()


def _polygon_d(points: list[tuple[float, float]]) -> str:
    head = f"M{points[0][0]:.2f},{points[0][1]:.2f}"
    rest = "".join(f"L{x:.2f},{y:.2f}" for x, y in points[1:])
    return f"{head}{rest}Z"


def _regular_points(sides: int) -> list[tuple[float, float]]:
    """A regular polygon on the unit circle, clockwise from the top.

    Rotated by half a turn when the side count is even, so the figure sits on a
    flat edge rather than balancing on a point -- which is how a hexagon is
    drawn everywhere a child has seen one.
    """
    turn = 2 * math.pi / sides
    offset = -math.pi / 2 + (turn / 2 if sides % 2 == 0 else 0.0)
    return [(math.cos(offset + turn * i), math.sin(offset + turn * i)) for i in range(sides)]


def _regular_polygon(sides: int) -> tuple[tuple[float, float], ...]:
    """The same polygon, rescaled to fill the unit box on both axes.

    Safe to stretch here because the box it is later drawn in is given this
    polygon's own proportions; see `_natural_ratio`.
    """
    raw = _regular_points(sides)
    xs = [p[0] for p in raw]
    ys = [p[1] for p in raw]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    return tuple(((x - min(xs)) / span_x, (y - min(ys)) / span_y) for x, y in raw)


def _unit_vertices(shape: ShapeName) -> tuple[tuple[float, float], ...]:
    if shape in _REGULAR:
        return _regular_polygon(_REGULAR[shape])
    return _UNIT_SHAPES[shape]


def _natural_ratio(shape: ShapeName) -> float:
    """How wide this shape is drawn relative to its height, by default.

    A regular polygon's own vertices settle it: a flat-topped hexagon is wider
    than it is tall by exactly the ratio of its spans, and drawing it in any
    other box makes it an irregular hexagon.
    """
    if shape in _REGULAR:
        raw = _regular_points(_REGULAR[shape])
        xs = [p[0] for p in raw]
        ys = [p[1] for p in raw]
        return (max(xs) - min(xs)) / (max(ys) - min(ys))
    return _NATURAL_RATIO[shape]


class ShapeFigure(BaseModel):
    """A named plane figure, optionally labelled the way a textbook labels one.

    Side and vertex labels are plain strings rather than authored in both
    locales, and that is a claim about what actually goes there: `3 cm`, `A`,
    `g`, `x`. A label that needs translating is a sentence, and a sentence
    belongs in the prompt where a reader can find it.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["shape"] = "shape"
    alt: AuthoredText
    shape: ShapeName

    # One per side, in drawing order; an empty string leaves that side unnamed.
    sides: tuple[str, ...] = ()
    # One per vertex, same rule. Used for "vinkel A", not for decoration.
    vertices: tuple[str, ...] = ()
    # Vertex indices to mark with the little square. A right angle a pupil is
    # meant to use has to be visible; one they are meant to spot the absence of
    # must not be drawn.
    right_angles: tuple[int, ...] = ()
    # Draws the altitude as a dashed line with this label. Only where the base
    # is unambiguous.
    height: str | None = None
    # Width divided by height, for the shapes where squashing keeps the name
    # honest. Unset means the shape's own proportions, which is nearly always
    # what is wanted -- this is for the long thin rectangle a question is
    # explicitly about.
    ratio: float | None = Field(default=None, gt=0.2, lt=5.0)
    # Fills the shape. For "how much of it" questions, where the outline alone
    # says nothing.
    shaded: bool = False
    # Circles only: draws the radius or the diameter, labelled.
    radius: str | None = None
    diameter: str | None = None
    # Rectangles and squares only: dashed lines dividing the width, each at a
    # fraction of it from the left, for "split the garden into 10 m and 2 m".
    # `part_labels` names each part under the bottom edge, so it takes the
    # bottom side's place and the two are not given together.
    divide_at: tuple[float, ...] = ()
    part_labels: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> ShapeFigure:
        count = _vertex_count(self.shape)
        if self.shape == "circle":
            if self.sides or self.vertices or self.right_angles or self.height:
                raise ValueError("a circle has no sides, vertices or altitude")
            if self.radius and self.diameter:
                raise ValueError("draw the radius or the diameter, not both")
        else:
            if self.radius or self.diameter:
                raise ValueError(f"{self.shape} has no radius or diameter")
            if self.sides and len(self.sides) != count:
                raise ValueError(f"{self.shape} has {count} sides, got {len(self.sides)} labels")
            if self.vertices and len(self.vertices) != count:
                raise ValueError(
                    f"{self.shape} has {count} vertices, got {len(self.vertices)} labels"
                )
            if any(not 0 <= i < count for i in self.right_angles):
                raise ValueError(f"{self.shape} has no vertex {max(self.right_angles)}")
            if self.height is not None and self.shape not in _APEX:
                raise ValueError(f"{self.shape} has no unambiguous base to measure a height from")
        if self.ratio is not None and self.shape not in _STRETCHABLE:
            raise ValueError(f"{self.shape} cannot be stretched without becoming another shape")
        # Refused here rather than squeezed in `_draw_shape`: a label too long
        # to leave the shape its minimum width is an authoring mistake, and it
        # should stop the file loading, as `MAX_BOX_LABEL` does for a box.
        for index, text in enumerate(self.sides):
            beside = _side_faces(self.shape, self.drawn_ratio, index) != "middle"
            if text and beside and SIDE_GAP + _label_width(text) > MAX_SIDE_MARGIN:
                raise ValueError(
                    f"side label {text!r} is too long to sit beside the {self.shape}; "
                    f"keep it to {MAX_BESIDE_LABEL} characters"
                )
        self._check_parts()
        return self

    def _check_parts(self) -> None:
        if not (self.divide_at or self.part_labels):
            return
        if self.shape not in _DIVISIBLE:
            raise ValueError(f"only a rectangle or a square can be divided, not a {self.shape}")
        cuts = list(self.divide_at)
        if not cuts or cuts != sorted(set(cuts)) or not all(0 < cut < 1 for cut in cuts):
            raise ValueError("divide_at is fractions of the width, rising, each between 0 and 1")
        if not self.part_labels:
            return
        if len(self.part_labels) != len(cuts) + 1:
            raise ValueError(
                f"{len(cuts)} dividing lines make {len(cuts) + 1} parts, "
                f"got {len(self.part_labels)} part labels"
            )
        if len(self.sides) > 2 and self.sides[2]:
            raise ValueError("part labels sit under the bottom edge, so it takes no side label")
        # Each label centred on its part; neighbours must not run into each
        # other. Worked out on the drawn width, which is what the pupil sees.
        width = _shape_frame(self)[2]
        edges = [0.0, *cuts, 1.0]
        centres = [(a + b) / 2 * width for a, b in zip(edges, edges[1:], strict=False)]
        for (c1, t1), (c2, t2) in zip(
            zip(centres, self.part_labels, strict=True),
            zip(centres[1:], self.part_labels[1:], strict=True),
            strict=False,
        ):
            if c1 + _label_width(t1) / 2 + LABEL_GAP > c2 - _label_width(t2) / 2:
                raise ValueError(
                    f"part labels {t1!r} and {t2!r} would overlap; "
                    "the parts are too narrow for them"
                )

    @property
    def drawn_ratio(self) -> float:
        return self.ratio if self.ratio is not None else _natural_ratio(self.shape)


class CountersFigure(BaseModel):
    """Things to count, and optionally to see grouped.

    The row of dots a counting question already draws in its prompt with `●`,
    except it wraps, it can be split into equal groups, and some of it can be
    shaded -- which is what turns counting into multiplication, division or a
    part of a whole without a second kind of figure.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["counters"] = "counters"
    alt: AuthoredText
    count: int = Field(ge=1, le=MAX_COUNTERS)
    # Equal groups, drawn with a gap between them. `[4, 4, 4]` is what "three
    # groups of four" looks like before anyone writes 3 × 4.
    groups: tuple[int, ...] = ()
    per_row: int = Field(default=10, ge=1, le=10)
    shaded: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check(self) -> CountersFigure:
        if self.shaded > self.count:
            raise ValueError(f"{self.shaded} shaded of {self.count} counters")
        if self.groups:
            if sum(self.groups) != self.count:
                raise ValueError(f"groups {self.groups} do not add up to {self.count}")
            if any(size < 1 for size in self.groups):
                raise ValueError("an empty group is not a group")
        return self


class ArrayFigure(BaseModel):
    """A rectangle made of unit squares. The one figure that is to scale.

    Area before the formula, and multiplication as a rectangle rather than as a
    rule -- which is exactly how LK20 frames it at 3. and 4. trinn. Because the
    cells are square and countable, a pupil who does not yet trust `3 · 4` can
    get there by counting, and see afterwards that the counting agreed.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["array"] = "array"
    alt: AuthoredText
    rows: int = Field(ge=1, le=MAX_ARRAY_SIDE)
    columns: int = Field(ge=1, le=MAX_ARRAY_SIDE)
    # Fills the first N cells, reading order. For "how many are coloured in".
    shaded: int = Field(default=0, ge=0)
    row_label: str | None = None
    column_label: str | None = None

    @model_validator(mode="after")
    def _check(self) -> ArrayFigure:
        if self.shaded > self.rows * self.columns:
            raise ValueError(f"{self.shaded} shaded of {self.rows * self.columns} cells")
        return self


class FractionRow(BaseModel):
    """One whole, cut into equal parts, some of them filled."""

    model_config = ConfigDict(frozen=True)

    parts: int = Field(ge=2, le=MAX_PARTS)
    shaded: int = Field(default=0, ge=0)
    label: str | None = None

    @model_validator(mode="after")
    def _check(self) -> FractionRow:
        if self.shaded > self.parts:
            raise ValueError(f"{self.shaded} shaded of {self.parts} parts")
        return self


class FractionFigure(BaseModel):
    """One or more wholes cut into parts, as bars or as circles.

    More than one row because the questions that need a picture most are the
    comparisons -- is 1/2 the same as 2/4 -- and two fractions drawn on the same
    width answer that by looking. A single row is the common case and reads as
    the pizza it usually is.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["fraction"] = "fraction"
    alt: AuthoredText
    shape: Literal["bar", "circle"] = "bar"
    rows: tuple[FractionRow, ...] = Field(min_length=1, max_length=MAX_ROWS)


class NumberLineMark(BaseModel):
    """A point called out on the line."""

    model_config = ConfigDict(frozen=True)

    at: float
    label: str | None = None
    # An unknown is drawn hollow with a "?" rather than solid: the question is
    # which number sits there, and a filled dot looks like an answer.
    unknown: bool = False


class NumberLineJump(BaseModel):
    """An arc from one number to another, the way jumps are taught.

    Directed: `start` above `end` draws the arc pointing left, because counting
    backwards is a different thing from counting forwards and a picture that
    hides which way it went has lost the part being learned.
    """

    model_config = ConfigDict(frozen=True)

    start: float
    end: float
    label: str | None = None

    @model_validator(mode="after")
    def _check(self) -> NumberLineJump:
        if self.start == self.end:
            raise ValueError("a jump that goes nowhere is not a jump")
        return self


class NumberLineFigure(BaseModel):
    """A ruled line, with marks and jumps on it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["number_line"] = "number_line"
    alt: AuthoredText
    start: float
    end: float
    step: float = Field(gt=0)
    # Label every Nth tick. Ten ticks with ten numbers under them is unreadable
    # at phone width; every fifth is a ruler.
    label_every: int = Field(default=1, ge=1)
    marks: tuple[NumberLineMark, ...] = ()
    jumps: tuple[NumberLineJump, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> NumberLineFigure:
        if self.end <= self.start:
            raise ValueError("a number line runs left to right")
        span = (self.end - self.start) / self.step
        if abs(span - round(span)) > 1e-6:
            raise ValueError(f"{self.step} does not divide {self.start}..{self.end} evenly")
        if round(span) + 1 > MAX_TICKS:
            raise ValueError(f"{round(span) + 1} ticks is more than a page can show")
        for value in [m.at for m in self.marks] + [v for j in self.jumps for v in (j.start, j.end)]:
            if not self.start <= value <= self.end:
                raise ValueError(f"{value} is off the end of the line")
        return self


# A box whose longest edge is more than this many times its shortest is drawn
# as a plank or a sheet, which no longer reads as a box.
MAX_BOX_SPREAD = 6.0
# The height and width labels both sit beside the box, as a shape's left and
# right side labels do, so the same limit keeps the box `MIN_SHAPE_WIDTH` wide.
MAX_BOX_LABEL = MAX_BESIDE_LABEL
# How far the depth recedes per unit of width, along each axis: half scale at
# 45 degrees, the cabinet projection textbooks use.
BOX_DEPTH = 0.5 * math.cos(math.pi / 4)


class BoxFigure(BaseModel):
    """A rectangular box -- a cuboid, or a cube -- labelled on three edges.

    Drawn in cabinet projection, the way a textbook draws one: the front face at
    true size, the depth receding up and to the right at half scale, and the
    three edges hidden behind the box dashed. Drawn to its own proportions, so
    a cube looks like a cube and a long box looks long.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["box"] = "box"
    alt: AuthoredText
    # Left to right along the front, front to back, and bottom to top. In any
    # unit: only their proportions are drawn.
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    length_label: str | None = Field(default=None, max_length=MAX_BOX_LABEL)
    width_label: str | None = Field(default=None, max_length=MAX_BOX_LABEL)
    height_label: str | None = Field(default=None, max_length=MAX_BOX_LABEL)

    @model_validator(mode="after")
    def _check(self) -> BoxFigure:
        edges = (self.length, self.width, self.height)
        if max(edges) / min(edges) > MAX_BOX_SPREAD:
            raise ValueError(
                f"a {self.length} by {self.width} by {self.height} box is drawn as a "
                f"plank; keep the longest edge within {MAX_BOX_SPREAD:g} times the shortest"
            )
        return self


# How round the ends of a cylinder look: the ellipse's height as a share of its
# width. A textbook's view from a little above.
CYLINDER_TILT = 0.3


class CylinderFigure(BaseModel):
    """An upright cylinder with its radius or diameter and its height labelled.

    The top is a full ellipse; the bottom shows its front half solid and its
    back half dashed, the edge nobody can see. Drawn to its own proportions,
    with the same spread limit as a box: a cylinder far wider than it is tall is
    a coin, and one far taller is a pipe.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["cylinder"] = "cylinder"
    alt: AuthoredText
    # In any unit: only their proportions are drawn.
    radius: float = Field(gt=0)
    height: float = Field(gt=0)
    # Drawn across the top: from the centre to the rim, or rim to rim.
    radius_label: str | None = Field(default=None, max_length=MAX_BOX_LABEL)
    diameter_label: str | None = Field(default=None, max_length=MAX_BOX_LABEL)
    # Beside the left side, as a box's height is.
    height_label: str | None = Field(default=None, max_length=MAX_BOX_LABEL)

    @model_validator(mode="after")
    def _check(self) -> CylinderFigure:
        if self.radius_label and self.diameter_label:
            raise ValueError("label the radius or the diameter, not both")
        across = 2 * self.radius
        if max(across, self.height) / min(across, self.height) > MAX_BOX_SPREAD:
            raise ValueError(
                f"a cylinder {across:g} across and {self.height:g} tall is a coin or a "
                f"pipe; keep one within {MAX_BOX_SPREAD:g} times the other"
            )
        return self


# Space between the two triangles of a `similar` figure.
SIMILAR_GAP = 20.0
# Two angles closer than this, in degrees, are the same angle and get the same
# mark: an author's 0.5 apex is an isosceles triangle, and its base angles must
# not be marked as if they differed.
SAME_ANGLE = 0.5


class SimilarFigure(BaseModel):
    """A triangle and a larger copy of it, side by side, with matching angles marked.

    The textbook picture of "same angles, longer sides". Each angle of the small
    triangle carries one, two or three arcs, and the same angle of the large one
    carries the same number, so the pupil can see which angles correspond. Two
    equal angles carry the same mark, and a right angle carries the square.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["similar"] = "similar"
    alt: AuthoredText
    # How many times larger the second triangle is. Up to three: beyond that the
    # small one is too small to read its marks.
    scale: float = Field(gt=1, le=3)
    # Where the top vertex sits along the base, from 0 (above the left end: a
    # right triangle) to 1. The defaults give angles of about 77, 57 and 46
    # degrees: every angle differs, by enough to see.
    apex: float = Field(default=0.2, ge=0, le=1)
    # Base length divided by height.
    ratio: float = Field(default=1.2, ge=0.5, le=2.5)
    angle_marks: bool = True


# Matchstick patterns: the most figures one picture shows, the room for each
# figure's number at the left of its row, the space between rows, how much of
# each end a stick leaves bare so two sticks meeting at a corner read as two,
# and the size of a stick's head. Two heads meet at every square's top-right
# corner, INSET * sqrt(2) apart, so INSET must exceed HEAD * sqrt(2) or they
# fuse into one blob.
MAX_MATCHSTICK_STAGES = 5
MATCHSTICK_LABEL = 16.0
MATCHSTICK_ROW_GAP = 10.0
MATCHSTICK_INSET = 3.5
MATCHSTICK_HEAD = 2.2


class MatchstickFigure(BaseModel):
    """A growing pattern of matchstick squares: figure 1, figure 2, and so on.

    Figure k is k squares in a row sharing their sides, so it takes 3k + 1
    sticks, and the rows stack top to bottom with each figure's number at the
    left. Every stick is drawn separately, shortened at both ends and with a
    head, so a pupil can count them, including the ones two squares share.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["matchsticks"] = "matchsticks"
    alt: AuthoredText
    stages: int = Field(ge=1, le=MAX_MATCHSTICK_STAGES)


Figure = Annotated[
    ShapeFigure
    | CountersFigure
    | ArrayFigure
    | FractionFigure
    | NumberLineFigure
    | BoxFigure
    | CylinderFigure
    | SimilarFigure
    | MatchstickFigure,
    Field(discriminator="kind"),
]


# --- drawing -----------------------------------------------------------------
#
# Everything below turns a validated figure into primitives. It is arithmetic
# with no branching on locale, no I/O and no state, which is what makes a test
# able to assert that 2/4 shades half the bar.


def draw(figure: Figure, locale: str) -> Drawing:
    """Resolve a figure to primitives, with its alt text in `locale`."""
    alt = figure.alt.get(locale)
    if isinstance(figure, ShapeFigure):
        return _draw_shape(figure, alt)
    if isinstance(figure, CountersFigure):
        return _draw_counters(figure, alt)
    if isinstance(figure, ArrayFigure):
        return _draw_array(figure, alt)
    if isinstance(figure, BoxFigure):
        return _draw_box(figure, alt)
    if isinstance(figure, CylinderFigure):
        return _draw_cylinder(figure, alt)
    if isinstance(figure, SimilarFigure):
        return _draw_similar(figure, alt)
    if isinstance(figure, MatchstickFigure):
        return _draw_matchsticks(figure, alt)
    if isinstance(figure, FractionFigure):
        return _draw_fraction(figure, alt)
    return _draw_number_line(figure, alt)


def _shape_frame(figure: ShapeFigure) -> tuple[float, float, float, float]:
    """Left, top, width and height of the box a polygon is drawn in."""
    ratio = figure.drawn_ratio
    # A label beside a left or right side runs away from the shape, so the
    # sides need room for the longest one: "102 cm" is far wider than PAD.
    beside = [
        text
        for index, text in enumerate(figure.sides)
        if text and _side_faces(figure.shape, ratio, index) != "middle"
    ]
    margin = max([PAD, *(SIDE_GAP + _label_width(text) for text in beside)])
    width = min(VIEW - 2 * margin, (VIEW - 2 * PAD) * ratio)
    height = width / ratio
    return (VIEW - width) / 2, (VIEW - height) / 2, width, height


def _draw_shape(figure: ShapeFigure, alt: str) -> Drawing:
    if figure.shape == "circle":
        return _draw_circle(figure, alt)

    ratio = figure.drawn_ratio
    left, top, width, height = _shape_frame(figure)
    points = [(left + ux * width, top + uy * height) for ux, uy in _unit_vertices(figure.shape)]
    centre = (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )

    paths = [Path(_polygon_d(points), "fill" if figure.shaded else "outline")]
    labels: list[Label] = []

    # Side labels sit just outside the midpoint of their side, pushed away from
    # the centre so a label never lands on the shape it belongs to.
    for index, text in enumerate(figure.sides):
        if not text:
            continue
        ax, ay = points[index]
        bx, by = points[(index + 1) % len(points)]
        mid = ((ax + bx) / 2, (ay + by) / 2)
        anchor = _side_faces(figure.shape, ratio, index)
        labels.append(Label(*_pushed_out(mid, centre, SIDE_GAP), text, anchor=anchor))

    for index, text in enumerate(figure.vertices):
        if not text:
            continue
        labels.append(Label(*_pushed_out(points[index], centre, LABEL_SIZE), text))

    paths.extend(_right_angle_mark(points, index) for index in figure.right_angles)

    bottom = top + height
    for cut in figure.divide_at:
        x = left + cut * width
        paths.append(Path(f"M{x:.2f},{top:.2f}L{x:.2f},{bottom:.2f}", "guide"))
    if figure.part_labels:
        edges = [0.0, *figure.divide_at, 1.0]
        parts = zip(edges, edges[1:], strict=False)
        for (a, b), text in zip(parts, figure.part_labels, strict=True):
            labels.append(Label(left + (a + b) / 2 * width, bottom + SIDE_GAP, text))

    if figure.height is not None:
        apex = points[_APEX[figure.shape]]
        foot = (apex[0], top + height)
        paths.append(Path(f"M{apex[0]:.2f},{apex[1]:.2f}L{foot[0]:.2f},{foot[1]:.2f}", "guide"))
        labels.append(
            Label(
                apex[0] + LABEL_SIZE * 0.6,
                (apex[1] + foot[1]) / 2,
                figure.height,
                anchor="start",
            )
        )

    return Drawing(VIEW, VIEW, alt, tuple(paths), (), tuple(labels))


def _draw_box(figure: BoxFigure, alt: str) -> Drawing:
    # The height label runs left of the front face and the width label right of
    # the receding edge, so the sides make room for them as `_draw_shape` does.
    left = max(PAD, SIDE_GAP + _label_width(figure.height_label or ""))
    right = max(PAD, SIDE_GAP + _label_width(figure.width_label or ""))
    room_x, room_y = VIEW - left - right, VIEW - 2 * PAD

    # The drawing's extent in the figure's own units, then one scale for both
    # axes so the proportions survive.
    depth = figure.width * BOX_DEPTH
    scale = min(room_x / (figure.length + depth), room_y / (figure.height + depth))
    length, height, depth = figure.length * scale, figure.height * scale, depth * scale

    x0 = left + (room_x - length - depth) / 2
    y0 = PAD + (room_y - height - depth) / 2 + depth
    ftl, ftr = (x0, y0), (x0 + length, y0)
    fbl, fbr = (x0, y0 + height), (x0 + length, y0 + height)

    def back(point: tuple[float, float]) -> tuple[float, float]:
        return point[0] + depth, point[1] - depth

    paths = [
        Path(_polygon_d([ftl, ftr, fbr, fbl]), "outline"),
        Path(_polygon_d([ftl, back(ftl), back(ftr), ftr]), "outline"),
        Path(_polygon_d([ftr, back(ftr), back(fbr), fbr]), "outline"),
    ]
    # The three edges meeting at the corner nobody can see.
    hidden = back(fbl)
    for end in (fbl, back(ftl), back(fbr)):
        paths.append(Path(f"M{hidden[0]:.2f},{hidden[1]:.2f}L{end[0]:.2f},{end[1]:.2f}", "guide"))

    labels: list[Label] = []
    if figure.length_label:
        labels.append(Label(x0 + length / 2, fbl[1] + SIDE_GAP, figure.length_label))
    if figure.height_label:
        labels.append(
            Label(x0 - SIDE_GAP * 0.6, y0 + height / 2, figure.height_label, anchor="end")
        )
    if figure.width_label:
        labels.append(
            Label(
                fbr[0] + depth / 2 + SIDE_GAP * 0.6,
                fbr[1] - depth / 2 + SIDE_GAP * 0.4,
                figure.width_label,
                anchor="start",
            )
        )

    return Drawing(VIEW, VIEW, alt, tuple(paths), (), tuple(labels))


def _draw_cylinder(figure: CylinderFigure, alt: str) -> Drawing:
    # The height label runs left of the cylinder, so the left side makes room.
    left = max(PAD, SIDE_GAP + _label_width(figure.height_label or ""))
    room_x, room_y = VIEW - left - PAD, VIEW - 2 * PAD

    # Extent in the figure's own units: two radii across, and the height plus
    # half an ellipse above and below. One scale keeps the proportions.
    tilt = figure.radius * CYLINDER_TILT
    scale = min(room_x / (2 * figure.radius), room_y / (figure.height + 2 * tilt))
    rx, ry, height = figure.radius * scale, tilt * scale, figure.height * scale

    cx = left + room_x / 2
    top = PAD + (room_y - height - 2 * ry) / 2 + ry
    bottom = top + height
    west, east = cx - rx, cx + rx

    def arc(y: float, sweep: int) -> str:
        return f"M{west:.2f},{y:.2f}A{rx:.2f},{ry:.2f} 0 0 {sweep} {east:.2f},{y:.2f}"

    paths = [
        # The whole top: its back half, then back along its front half.
        Path(f"{arc(top, 1)}A{rx:.2f},{ry:.2f} 0 0 1 {west:.2f},{top:.2f}Z", "outline"),
        Path(f"M{west:.2f},{top:.2f}L{west:.2f},{bottom:.2f}", "outline"),
        Path(f"M{east:.2f},{top:.2f}L{east:.2f},{bottom:.2f}", "outline"),
        # The bottom rim: the front half seen, the back half behind the cylinder.
        Path(arc(bottom, 0), "outline"),
        Path(arc(bottom, 1), "guide"),
    ]
    labels: list[Label] = []
    dots: tuple[Dot, ...] = ()
    if figure.radius_label or figure.diameter_label:
        start = cx if figure.radius_label else west
        paths.append(Path(f"M{start:.2f},{top:.2f}L{east:.2f},{top:.2f}", "guide"))
        text = figure.radius_label or figure.diameter_label or ""
        labels.append(Label((start + east) / 2, top - ry - SIDE_GAP * 0.6, text))
        dots = (Dot(cx, top, 2.5),)
    if figure.height_label:
        labels.append(
            Label(west - SIDE_GAP * 0.6, (top + bottom) / 2, figure.height_label, anchor="end")
        )
    return Drawing(VIEW, VIEW, alt, tuple(paths), dots, tuple(labels))


def _draw_similar(figure: SimilarFigure, alt: str) -> Drawing:
    # One unit triangle, base `ratio` wide and 1 tall; the large copy is the same
    # triangle times `scale`. One scale fits both, bottom-aligned with a gap.
    unit = [(figure.apex * figure.ratio, 0.0), (figure.ratio, 1.0), (0.0, 1.0)]
    room = VIEW - 2 * PAD
    size = min((room - SIMILAR_GAP) / (figure.ratio * (1 + figure.scale)), room / figure.scale)
    small_w = figure.ratio * size
    total_w = small_w * (1 + figure.scale) + SIMILAR_GAP
    base = (VIEW + size * figure.scale) / 2
    small_left = (VIEW - total_w) / 2
    large_left = small_left + small_w + SIMILAR_GAP

    def place(left: float, factor: float) -> list[tuple[float, float]]:
        height = size * factor
        return [(left + x * size * factor, base - height + y * height) for x, y in unit]

    marks = _angle_marks(unit) if figure.angle_marks else (0, 0, 0)
    paths: list[Path] = []
    for points in (place(small_left, 1.0), place(large_left, figure.scale)):
        paths.append(Path(_polygon_d(points), "outline"))
        for index, count in enumerate(marks):
            if count < 0:
                paths.append(_right_angle_mark(points, index))
            elif count:
                paths.extend(_angle_arcs(points, index, count))
    return Drawing(VIEW, VIEW, alt, tuple(paths))


def _angle_marks(points: list[tuple[float, float]]) -> tuple[int, ...]:
    """How many arcs each angle carries: one per distinct angle, -1 for a right one."""
    angles = [_angle_at(points, index) for index in range(len(points))]
    distinct: list[float] = []
    marks = []
    for angle in angles:
        if abs(angle - 90) < SAME_ANGLE:
            marks.append(-1)
            continue
        match = next((i for i, seen in enumerate(distinct) if abs(seen - angle) < SAME_ANGLE), None)
        if match is None:
            distinct.append(angle)
            match = len(distinct) - 1
        marks.append(match + 1)
    return tuple(marks)


def _angle_at(points: list[tuple[float, float]], index: int) -> float:
    corner = points[index]
    before = points[(index - 1) % len(points)]
    after = points[(index + 1) % len(points)]
    a = math.atan2(before[1] - corner[1], before[0] - corner[0])
    b = math.atan2(after[1] - corner[1], after[0] - corner[0])
    turn = abs(math.degrees(a - b)) % 360
    return min(turn, 360 - turn)


def _angle_arcs(points: list[tuple[float, float]], index: int, count: int) -> list[Path]:
    """`count` concentric arcs inside one corner, sized to the corner's shorter side."""
    corner = points[index]
    before = points[(index - 1) % len(points)]
    after = points[(index + 1) % len(points)]
    radius = min(14.0, 0.22 * min(math.dist(corner, before), math.dist(corner, after)))
    step = max(2.0, radius * 0.25)
    # Which way round the circle is the inside of the angle, in SVG's y-down
    # space: clockwise on screen when `after` is clockwise of `before`.
    cross = (before[0] - corner[0]) * (after[1] - corner[1]) - (before[1] - corner[1]) * (
        after[0] - corner[0]
    )
    sweep = 1 if cross > 0 else 0
    arcs = []
    for ring in range(count):
        r = radius + ring * step
        one, two = _towards(corner, before, r), _towards(corner, after, r)
        arcs.append(
            Path(
                f"M{one[0]:.2f},{one[1]:.2f}A{r:.2f},{r:.2f} 0 0 {sweep} {two[0]:.2f},{two[1]:.2f}",
                "guide",
            )
        )
    return arcs


def _draw_matchsticks(figure: MatchstickFigure, alt: str) -> Drawing:
    stages = figure.stages
    room_x = VIEW - 2 * PAD - MATCHSTICK_LABEL
    room_y = VIEW - 2 * PAD - (stages - 1) * MATCHSTICK_ROW_GAP
    side = min(room_x / stages, room_y / stages)
    left = PAD + MATCHSTICK_LABEL
    top = (VIEW - stages * side - (stages - 1) * MATCHSTICK_ROW_GAP) / 2

    paths: list[Path] = []
    dots: list[Dot] = []
    labels: list[Label] = []

    def stick(x1: float, y1: float, x2: float, y2: float) -> None:
        # Bare at both ends, so sticks meeting at a corner do not touch; the
        # head at the right-hand or top end, as a matchstick lies on a table.
        a, b = (
            _towards((x1, y1), (x2, y2), MATCHSTICK_INSET),
            _towards((x2, y2), (x1, y1), MATCHSTICK_INSET),
        )
        paths.append(Path(f"M{a[0]:.2f},{a[1]:.2f}L{b[0]:.2f},{b[1]:.2f}", "outline"))
        dots.append(Dot(b[0], b[1], MATCHSTICK_HEAD))

    for row in range(stages):
        squares = row + 1
        y = top + row * (side + MATCHSTICK_ROW_GAP)
        for i in range(squares):
            x = left + i * side
            stick(x, y, x + side, y)
            stick(x, y + side, x + side, y + side)
        for i in range(squares + 1):
            x = left + i * side
            stick(x, y + side, x, y)
        labels.append(Label(left - MATCHSTICK_LABEL / 2, y + side / 2, str(squares)))

    return Drawing(VIEW, VIEW, alt, tuple(paths), tuple(dots), tuple(labels))


def _draw_circle(figure: ShapeFigure, alt: str) -> Drawing:
    r = (VIEW - 2 * PAD) / 2
    cx = cy = VIEW / 2
    paths = [
        Path(
            f"M{cx - r:.2f},{cy:.2f}A{r:.2f},{r:.2f} 0 1 0 {cx + r:.2f},{cy:.2f}"
            f"A{r:.2f},{r:.2f} 0 1 0 {cx - r:.2f},{cy:.2f}Z",
            "fill" if figure.shaded else "outline",
        )
    ]
    labels: list[Label] = []
    if figure.radius:
        paths.append(Path(f"M{cx:.2f},{cy:.2f}L{cx + r:.2f},{cy:.2f}", "guide"))
        labels.append(Label(cx + r / 2, cy - LABEL_SIZE * 0.7, figure.radius))
    if figure.diameter:
        paths.append(Path(f"M{cx - r:.2f},{cy:.2f}L{cx + r:.2f},{cy:.2f}", "guide"))
        labels.append(Label(cx, cy - LABEL_SIZE * 0.7, figure.diameter))
    dots = (Dot(cx, cy, 2.5),) if (figure.radius or figure.diameter) else ()
    return Drawing(VIEW, VIEW, alt, tuple(paths), dots, tuple(labels))


def _side_faces(shape: ShapeName, ratio: float, index: int) -> str:
    """Which way a side's label runs: "start" rightwards, "end" leftwards, or centred.

    Read off the unit shape stretched to `ratio`, which points the same way as
    the drawn one: only the scale differs.
    """
    unit = [(x * ratio, y) for x, y in _unit_vertices(shape)]
    cx = sum(x for x, _ in unit) / len(unit)
    cy = sum(y for _, y in unit) / len(unit)
    (ax, ay), (bx, by) = unit[index], unit[(index + 1) % len(unit)]
    dx, dy = (ax + bx) / 2 - cx, (ay + by) / 2 - cy
    if abs(dx) <= abs(dy):
        return "middle"
    return "start" if dx > 0 else "end"


def _label_width(text: str) -> float:
    """Roughly how wide a side label is drawn, in view units."""
    return len(text) * LABEL_SIZE * CHAR_WIDTH


def _pushed_out(
    point: tuple[float, float], centre: tuple[float, float], distance: float
) -> tuple[float, float]:
    """`point`, moved `distance` further from `centre`.

    Radially rather than by axis, so a label on a slanted side ends up beside
    that side instead of beside the one next to it.
    """
    dx, dy = point[0] - centre[0], point[1] - centre[1]
    length = math.hypot(dx, dy) or 1.0
    return point[0] + dx / length * distance, point[1] + dy / length * distance


def _right_angle_mark(points: list[tuple[float, float]], index: int) -> Path:
    """The little square, sized to the corner it sits in."""
    corner = points[index]
    before = points[(index - 1) % len(points)]
    after = points[(index + 1) % len(points)]
    size = RIGHT_ANGLE_FRACTION * min(math.dist(corner, before), math.dist(corner, after))
    one = _towards(corner, before, size)
    two = _towards(corner, after, size)
    joint = (one[0] + two[0] - corner[0], one[1] + two[1] - corner[1])
    return Path(
        f"M{one[0]:.2f},{one[1]:.2f}L{joint[0]:.2f},{joint[1]:.2f}L{two[0]:.2f},{two[1]:.2f}",
        "guide",
    )


def _towards(
    origin: tuple[float, float], target: tuple[float, float], distance: float
) -> tuple[float, float]:
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    length = math.hypot(dx, dy) or 1.0
    return origin[0] + dx / length * distance, origin[1] + dy / length * distance


def _draw_counters(figure: CountersFigure, alt: str) -> Drawing:
    # Groups are laid out one per row when they fit, because "three groups of
    # four" is a statement about rows. Ungrouped counters wrap at `per_row`.
    if figure.groups:
        rows = [list(range(size)) for size in figure.groups]
        gap_between_groups = True
    else:
        per_row = min(figure.per_row, figure.count)
        rows = [
            list(range(min(per_row, figure.count - start)))
            for start in range(0, figure.count, per_row)
        ]
        gap_between_groups = False

    spacing = 26.0
    radius = 9.0
    group_gap = 10.0 if gap_between_groups else 0.0
    widest = max(len(row) for row in rows)
    width = PAD * 2 + spacing * widest
    height = PAD + (spacing + group_gap) * len(rows)

    dots: list[Dot] = []
    drawn = 0
    for row_index, row in enumerate(rows):
        # Each row centred, so unequal rows read as one block rather than as a
        # staircase.
        row_width = spacing * len(row)
        left = (width - row_width) / 2 + spacing / 2
        y = PAD / 2 + spacing / 2 + row_index * (spacing + group_gap)
        for column in range(len(row)):
            dots.append(
                Dot(
                    left + column * spacing,
                    y,
                    radius,
                    "fill" if drawn < figure.shaded else "outline",
                )
            )
            drawn += 1

    return Drawing(width, height, alt, (), tuple(dots), ())


def _draw_array(figure: ArrayFigure, alt: str) -> Drawing:
    cell = min(
        (VIEW - 2 * PAD) / max(figure.rows, figure.columns),
        30.0,
    )
    grid_w, grid_h = cell * figure.columns, cell * figure.rows
    left = PAD
    top = PAD / 2

    paths: list[Path] = []
    index = 0
    for row in range(figure.rows):
        for column in range(figure.columns):
            x, y = left + column * cell, top + row * cell
            paths.append(
                Path(
                    _polygon_d([(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell)]),
                    "fill" if index < figure.shaded else "outline",
                )
            )
            index += 1

    labels: list[Label] = []
    if figure.column_label:
        labels.append(Label(left + grid_w / 2, top - LABEL_SIZE * 0.7, figure.column_label))
    if figure.row_label:
        labels.append(
            Label(
                left - LABEL_SIZE * 0.7,
                top + grid_h / 2,
                figure.row_label,
                anchor="end",
            )
        )

    width = left + grid_w + PAD
    height = top + grid_h + (LABEL_SIZE if figure.column_label else 0) + PAD / 2
    return Drawing(width, height, alt, tuple(paths), (), tuple(labels))


def _draw_fraction(figure: FractionFigure, alt: str) -> Drawing:
    if figure.shape == "circle":
        return _draw_fraction_circles(figure, alt)

    bar_h = 34.0
    gap = 16.0
    width = VIEW
    left, right = PAD / 2, VIEW - PAD / 2
    span = right - left
    labelled = any(row.label for row in figure.rows)
    label_w = 34.0 if labelled else 0.0

    paths: list[Path] = []
    labels: list[Label] = []
    for index, row in enumerate(figure.rows):
        top = PAD / 2 + index * (bar_h + gap)
        part_w = (span - label_w) / row.parts
        for part in range(row.parts):
            x = left + label_w + part * part_w
            paths.append(
                Path(
                    _polygon_d(
                        [(x, top), (x + part_w, top), (x + part_w, top + bar_h), (x, top + bar_h)]
                    ),
                    "fill" if part < row.shaded else "outline",
                )
            )
        if row.label:
            labels.append(Label(left, top + bar_h / 2, row.label, anchor="start"))

    height = PAD / 2 + len(figure.rows) * (bar_h + gap) - gap + PAD / 2
    return Drawing(width, height, alt, tuple(paths), (), tuple(labels))


def _draw_fraction_circles(figure: FractionFigure, alt: str) -> Drawing:
    r = 46.0
    gap = 22.0
    per = 2 * r + gap
    width = PAD + per * len(figure.rows)
    labelled = any(row.label for row in figure.rows)
    height = PAD + 2 * r + (LABEL_SIZE * 1.6 if labelled else 0.0)

    paths: list[Path] = []
    labels: list[Label] = []
    for index, row in enumerate(figure.rows):
        cx = PAD / 2 + gap / 2 + r + index * per
        cy = PAD / 2 + r
        for part in range(row.parts):
            paths.append(
                Path(
                    _wedge_d(cx, cy, r, part, row.parts),
                    "fill" if part < row.shaded else "outline",
                )
            )
        if row.label:
            labels.append(Label(cx, cy + r + LABEL_SIZE, row.label))

    return Drawing(width, height, alt, tuple(paths), (), tuple(labels))


def _wedge_d(cx: float, cy: float, r: float, index: int, parts: int) -> str:
    """One slice, starting at twelve o'clock and going clockwise.

    Clockwise from the top because that is how a cake is cut and how every
    fraction circle a pupil has seen is shaded -- anticlockwise would be
    correct and would look wrong.
    """
    turn = 2 * math.pi / parts
    a0 = -math.pi / 2 + index * turn
    a1 = a0 + turn
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if turn > math.pi else 0
    return f"M{cx:.2f},{cy:.2f}L{x0:.2f},{y0:.2f}A{r:.2f},{r:.2f} 0 {large} 1 {x1:.2f},{y1:.2f}Z"


def line_x(figure: NumberLineFigure, value: float) -> float:
    """Where a value sits along the drawn line, in view units.

    Module level rather than a closure inside `_draw_number_line` because the
    browser needs the same mapping in reverse: a pupil dragging a marker is
    answering in pixels, and the answer has to come back as a number. Keeping
    both directions here means the pair can be asserted without a browser.
    """
    left, right = PAD, VIEW - PAD
    return left + (right - left) * (value - figure.start) / (figure.end - figure.start)


def line_value(figure: NumberLineFigure, x: float) -> float:
    """The value at a point along the drawn line. The inverse of `line_x`."""
    left, right = PAD, VIEW - PAD
    return figure.start + (figure.end - figure.start) * (x - left) / (right - left)


def tick_count(figure: NumberLineFigure) -> int:
    """How many ticks the line carries, the last one included."""
    return round((figure.end - figure.start) / figure.step) + 1


def tick_index(figure: NumberLineFigure, value: float) -> int | None:
    """Which tick a value is, or None if it falls between two.

    Grading a dragged answer compares tick indices rather than the values
    themselves, because `start + 7 * 0.1` is not `0.7` in binary and a pupil who
    landed exactly right should not be marked wrong by the last bit of a float.
    Rejecting an off-tick value is the same check: a marker that snaps cannot
    produce one, so a response carrying one did not come from the line.
    """
    steps = (value - figure.start) / figure.step
    if abs(steps - round(steps)) > 1e-6:
        return None
    index = round(steps)
    if not 0 <= index < tick_count(figure):
        return None
    return index


def line_geometry(figure: NumberLineFigure) -> dict[str, float]:
    """The numbers a browser needs to put a marker where a pointer went.

    Handed to the template as data attributes rather than reimplemented in
    JavaScript: the constants that decide where the line is drawn live up top in
    this file, and a second copy of them in a script is a drift waiting to
    happen.
    """
    return {
        "left": PAD,
        "right": VIEW - PAD,
        "y": PAD / 2 + (JUMP_BAND if figure.jumps else 0.0),
        "start": figure.start,
        "end": figure.end,
        "step": figure.step,
    }


def _draw_number_line(figure: NumberLineFigure, alt: str) -> Drawing:
    ticks = tick_count(figure)
    left, right = PAD, VIEW - PAD
    # Jumps are drawn above the line, so the line only sits low when there are
    # any. An empty band of white above a bare number line looks like a bug.
    jump_band = JUMP_BAND if figure.jumps else 0.0
    y = PAD / 2 + jump_band

    def at(value: float) -> float:
        return line_x(figure, value)

    paths = [Path(f"M{left:.2f},{y:.2f}L{right:.2f},{y:.2f}", "axis")]
    labels: list[Label] = []
    for index in range(ticks):
        value = figure.start + index * figure.step
        x = at(value)
        tall = index % figure.label_every == 0
        paths.append(Path(f"M{x:.2f},{y - (7 if tall else 4):.2f}L{x:.2f},{y:.2f}", "axis"))
        if tall:
            labels.append(
                Label(x, y + TICK_SIZE, _number(value), size=TICK_SIZE, baseline="hanging")
            )

    dots: list[Dot] = []
    for mark in figure.marks:
        x = at(mark.at)
        dots.append(Dot(x, y, 5.0, "outline" if mark.unknown else "fill"))
        text = mark.label if mark.label is not None else ("?" if mark.unknown else None)
        if text:
            labels.append(Label(x, y - TICK_SIZE * 1.2, text, size=TICK_SIZE))

    for jump in figure.jumps:
        x0, x1 = at(jump.start), at(jump.end)
        peak = y - jump_band * 0.72
        # A quadratic through a control point twice the peak's offset lands the
        # curve on the peak, which is where the label goes.
        control_y = y - (y - peak) * 2
        paths.append(
            Path(f"M{x0:.2f},{y:.2f}Q{(x0 + x1) / 2:.2f},{control_y:.2f} {x1:.2f},{y:.2f}", "jump")
        )
        paths.append(_arrow_head(x1, y, forwards=x1 > x0))
        if jump.label:
            labels.append(Label((x0 + x1) / 2, peak - TICK_SIZE * 0.6, jump.label, size=TICK_SIZE))

    height = y + TICK_SIZE * 2 + PAD / 2
    return Drawing(VIEW, height, alt, tuple(paths), tuple(dots), tuple(labels))


def _arrow_head(x: float, y: float, *, forwards: bool) -> Path:
    """Which way the jump went, which is the whole point of drawing it."""
    reach = 6.0 if forwards else -6.0
    return Path(
        f"M{x - reach:.2f},{y - 5.0:.2f}L{x:.2f},{y:.2f}L{x - reach:.2f},{y + 5.0:.2f}",
        "jump-head",
    )


def _number(value: float) -> str:
    """A tick's number as a pupil writes it: no trailing zero, comma decimals."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", ",")
