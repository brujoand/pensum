"""The geometry behind a question's picture.

A figure is arithmetic with no I/O, so these assert the numbers rather than the
markup: that 2/4 shades half the bar, that a jump backwards points left, that a
3 by 4 array has twelve cells. A test that only checked the SVG parsed would
pass on a drawing that says the wrong thing.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from pensum.items.figures import (
    LABEL_SIZE,
    MAX_BESIDE_LABEL,
    MAX_BOX_LABEL,
    MIN_SHAPE_WIDTH,
    PAD,
    VIEW,
    ArrayFigure,
    BoxFigure,
    CountersFigure,
    CylinderFigure,
    FractionFigure,
    NumberLineFigure,
    ShapeFigure,
    _label_width,
    draw,
    line_geometry,
    line_value,
    line_x,
    tick_index,
)
from pensum.items.text import AuthoredText

ALT = AuthoredText(nb="En figur", en="A figure")


def shape(**kwargs) -> ShapeFigure:
    return ShapeFigure(alt=ALT, **kwargs)


# --- shapes ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "corners"),
    [
        ("triangle", 3),
        ("right_triangle", 3),
        ("square", 4),
        ("rectangle", 4),
        ("parallelogram", 4),
        ("rhombus", 4),
        ("trapezoid", 4),
        ("pentagon", 5),
        ("hexagon", 6),
        ("octagon", 8),
    ],
)
def test_a_polygon_is_drawn_with_the_corners_its_name_promises(name: str, corners: int) -> None:
    """The one property a shape figure must never get wrong."""
    drawing = draw(shape(shape=name), "nb")
    assert drawing.paths[0].d.count("L") == corners - 1


def test_every_shape_fits_inside_its_box() -> None:
    """A vertex outside the viewBox is a corner the browser silently clips."""
    for name in ("triangle", "hexagon", "rhombus", "trapezoid", "octagon"):
        for token in _coordinates(draw(shape(shape=name), "nb").paths[0].d):
            assert 0 <= token <= VIEW


@pytest.mark.parametrize("name", ["square", "rhombus", "pentagon", "hexagon", "octagon"])
def test_a_shape_is_drawn_in_its_own_proportions(name: str) -> None:
    """A square drawn in a rectangle's box is a rectangle. This is the check
    that a shared drawing box cannot silently rename a figure.
    """
    points = _coordinates(draw(shape(shape=name), "nb").paths[0].d)
    xs, ys = points[0::2], points[1::2]
    aspect = (max(xs) - min(xs)) / (max(ys) - min(ys))
    if name in ("square", "rhombus"):
        assert aspect == pytest.approx(1.0)
    else:
        # A regular polygon on a flat edge: wider than tall, by its own geometry
        # and never by more than the circle it is inscribed in.
        assert 1.0 <= aspect < 1.3


def test_side_labels_follow_the_sides() -> None:
    """Three labels on a triangle land in three different places."""
    drawing = draw(shape(shape="triangle", sides=("a", "b", "c")), "nb")
    placed = {label.text: (round(label.x), round(label.y)) for label in drawing.labels}
    assert set(placed) == {"a", "b", "c"}
    assert len(set(placed.values())) == 3


@pytest.mark.parametrize("ratio", [0.5, 1.0, 1.02, 1.6, 3.0])
def test_a_long_side_label_beside_the_shape_stays_in_view_and_off_the_outline(
    ratio: float,
) -> None:
    """A label on a left or right side runs away from the shape, and fits."""
    drawing = draw(
        shape(shape="rectangle", sides=("100 cm", "102 cm", "", "999 cm"), ratio=ratio), "nb"
    )
    xs = _coordinates(drawing.paths[0].d)[0::2]
    for label in drawing.labels:
        width = _label_width(label.text)
        if label.anchor == "start":
            assert label.x > max(xs)
            assert label.x + width <= VIEW
        elif label.anchor == "end":
            assert label.x < min(xs)
            assert label.x - width >= 0
        else:
            assert label.x - width / 2 >= 0 and label.x + width / 2 <= VIEW
    assert {label.anchor for label in drawing.labels} == {"middle", "start", "end"}


def test_a_rectangle_keeps_its_ratio_when_labels_narrow_it() -> None:
    drawing = draw(shape(shape="rectangle", sides=("", "102 cm", "", ""), ratio=1.6), "nb")
    points = _coordinates(drawing.paths[0].d)
    xs, ys = points[0::2], points[1::2]
    # The path is written to two decimals, so the ratio holds to about that.
    assert (max(xs) - min(xs)) / (max(ys) - min(ys)) == pytest.approx(1.6, abs=1e-3)


def test_a_side_label_too_long_to_sit_beside_a_shape_is_refused() -> None:
    """Otherwise the margin it needs would squeeze the shape to nothing."""
    too_long = "x" * (MAX_BESIDE_LABEL + 1)
    with pytest.raises(ValidationError, match="too long to sit beside"):
        shape(shape="rectangle", sides=("", too_long, "", ""))


def test_a_long_label_above_or_below_a_shape_is_not_refused() -> None:
    """Only a label beside the shape needs the margin; one above it does not."""
    shape(shape="rectangle", sides=("x" * (MAX_BESIDE_LABEL + 1), "", "", ""))


@pytest.mark.parametrize("ratio", [0.3, 1.0, 1.6, 4.0])
def test_the_longest_beside_labels_leave_the_shape_its_minimum_width(ratio: float) -> None:
    label = "x" * MAX_BESIDE_LABEL
    drawing = draw(shape(shape="rectangle", sides=("", label, "", label), ratio=ratio), "nb")
    xs = _coordinates(drawing.paths[0].d)[0::2]
    # A tall thin rectangle is narrower by its own ratio, not by its labels.
    expected = min(MIN_SHAPE_WIDTH, (VIEW - 2 * PAD) * ratio)
    assert max(xs) - min(xs) >= expected - 0.01


def test_an_empty_side_label_draws_nothing() -> None:
    """So an author can name one side of four without inventing names for the rest."""
    drawing = draw(shape(shape="square", sides=("4 cm", "", "", "")), "nb")
    assert [label.text for label in drawing.labels] == ["4 cm"]


def test_the_altitude_lands_on_the_base() -> None:
    drawing = draw(shape(shape="triangle", height="h"), "nb")
    guide = next(path for path in drawing.paths if path.role == "guide")
    top_x, _, foot_x, foot_y = _coordinates(guide.d)
    assert top_x == foot_x
    # The base is the lowest edge, so the foot is at the figure's bottom.
    assert foot_y == pytest.approx(max(_coordinates(drawing.paths[0].d)[1::2]))


def test_a_right_angle_mark_is_drawn_inside_the_corner() -> None:
    drawing = draw(shape(shape="right_triangle", right_angles=(2,)), "nb")
    mark = next(path for path in drawing.paths if path.role == "guide")
    assert mark.d.count("L") == 2


def test_alt_text_follows_the_locale() -> None:
    figure = ShapeFigure(shape="square", alt=AuthoredText(nb="Et kvadrat", en="A square"))
    assert draw(figure, "nb").alt == "Et kvadrat"
    assert draw(figure, "en").alt == "A square"


def test_a_circle_refuses_sides_and_a_polygon_refuses_a_radius() -> None:
    """The two mistakes a copy-pasted figure block actually makes."""
    with pytest.raises(ValidationError):
        shape(shape="circle", sides=("a",))
    with pytest.raises(ValidationError):
        shape(shape="square", radius="r")


def test_a_label_count_that_does_not_match_the_shape_is_refused() -> None:
    """Four labels on a triangle means the author was thinking of another figure."""
    with pytest.raises(ValidationError):
        shape(shape="triangle", sides=("a", "b", "c", "d"))
    with pytest.raises(ValidationError):
        shape(shape="pentagon", vertices=("A", "B", "C"))


def test_only_shapes_with_one_base_can_carry_a_height() -> None:
    with pytest.raises(ValidationError):
        shape(shape="hexagon", height="h")
    with pytest.raises(ValidationError):
        shape(shape="right_triangle", height="h")


def test_a_shape_that_would_stop_being_itself_cannot_be_stretched() -> None:
    with pytest.raises(ValidationError):
        shape(shape="square", ratio=2.0)
    with pytest.raises(ValidationError):
        shape(shape="hexagon", ratio=2.0)


# --- counters ----------------------------------------------------------------


def test_counters_draw_one_dot_each() -> None:
    assert len(draw(CountersFigure(alt=ALT, count=7), "nb").dots) == 7


def test_counters_wrap_rather_than_run_off_the_page() -> None:
    drawing = draw(CountersFigure(alt=ALT, count=23, per_row=10), "nb")
    assert len(drawing.dots) == 23
    assert len({round(dot.cy) for dot in drawing.dots}) == 3


def test_groups_are_drawn_one_per_row() -> None:
    """Three groups of four is a claim about rows, not just about a total."""
    drawing = draw(CountersFigure(alt=ALT, count=12, groups=(4, 4, 4)), "nb")
    rows = {round(dot.cy) for dot in drawing.dots}
    assert len(rows) == 3


def test_shaded_counters_come_first() -> None:
    drawing = draw(CountersFigure(alt=ALT, count=5, shaded=2), "nb")
    assert [dot.role for dot in drawing.dots] == ["fill", "fill", "outline", "outline", "outline"]


def test_groups_that_do_not_add_up_are_refused() -> None:
    with pytest.raises(ValidationError):
        CountersFigure(alt=ALT, count=12, groups=(4, 4))


def test_more_shaded_than_counters_is_refused() -> None:
    with pytest.raises(ValidationError):
        CountersFigure(alt=ALT, count=3, shaded=4)


# --- arrays ------------------------------------------------------------------


def test_an_array_draws_a_cell_per_square() -> None:
    drawing = draw(ArrayFigure(alt=ALT, rows=3, columns=4), "nb")
    assert len(drawing.paths) == 12


def test_array_cells_are_square() -> None:
    """The whole argument for this figure is that the area can be counted."""
    drawing = draw(ArrayFigure(alt=ALT, rows=2, columns=5), "nb")
    xs, ys = _coordinates(drawing.paths[0].d)[0::2], _coordinates(drawing.paths[0].d)[1::2]
    assert max(xs) - min(xs) == pytest.approx(max(ys) - min(ys))


def test_array_shading_fills_in_reading_order() -> None:
    drawing = draw(ArrayFigure(alt=ALT, rows=2, columns=3, shaded=4), "nb")
    assert [path.role for path in drawing.paths] == [
        "fill",
        "fill",
        "fill",
        "fill",
        "outline",
        "outline",
    ]


def test_more_shaded_than_cells_is_refused() -> None:
    with pytest.raises(ValidationError):
        ArrayFigure(alt=ALT, rows=2, columns=2, shaded=5)


# --- fractions ---------------------------------------------------------------


def test_a_fraction_bar_has_one_part_per_denominator() -> None:
    drawing = draw(FractionFigure(alt=ALT, rows=({"parts": 8, "shaded": 3},)), "nb")
    assert len(drawing.paths) == 8
    assert sum(path.role == "fill" for path in drawing.paths) == 3


def test_equivalent_fractions_shade_the_same_width() -> None:
    """The reason a comparison is drawn at all: 1/2 and 2/4 must look equal."""
    drawing = draw(
        FractionFigure(
            alt=ALT,
            rows=({"parts": 2, "shaded": 1}, {"parts": 4, "shaded": 2}),
        ),
        "nb",
    )
    halves = [p for p in drawing.paths[:2] if p.role == "fill"]
    quarters = [p for p in drawing.paths[2:] if p.role == "fill"]
    assert _width(halves) == pytest.approx(_width(quarters))


def test_fraction_circles_close_the_whole() -> None:
    """Six sixths must be a circle, not five sixths and a gap."""
    drawing = draw(FractionFigure(alt=ALT, shape="circle", rows=({"parts": 6, "shaded": 1},)), "nb")
    assert len(drawing.paths) == 6
    assert all(path.d.endswith("Z") for path in drawing.paths)


def test_shading_more_than_the_whole_is_refused() -> None:
    with pytest.raises(ValidationError):
        FractionFigure(alt=ALT, rows=({"parts": 4, "shaded": 5},))


# --- number lines ------------------------------------------------------------


def test_a_number_line_ticks_every_step() -> None:
    drawing = draw(NumberLineFigure(alt=ALT, start=0, end=10, step=1), "nb")
    # One path for the line itself, then one tick per value.
    assert len(drawing.paths) == 1 + 11
    assert [label.text for label in drawing.labels] == [str(n) for n in range(11)]


def test_label_every_thins_the_numbers_without_thinning_the_ticks() -> None:
    drawing = draw(NumberLineFigure(alt=ALT, start=0, end=100, step=5, label_every=4), "nb")
    assert len(drawing.paths) == 1 + 21
    assert [label.text for label in drawing.labels] == ["0", "20", "40", "60", "80", "100"]


def test_an_unknown_mark_is_hollow_and_asks() -> None:
    drawing = draw(
        NumberLineFigure(alt=ALT, start=0, end=10, step=1, marks=({"at": 4, "unknown": True},)),
        "nb",
    )
    assert [dot.role for dot in drawing.dots] == ["outline"]
    assert "?" in [label.text for label in drawing.labels]


def test_a_backwards_jump_points_backwards() -> None:
    """Which way the count went is the thing being taught."""
    forwards = _head(
        draw(
            NumberLineFigure(alt=ALT, start=0, end=10, step=1, jumps=({"start": 2, "end": 6},)),
            "nb",
        )
    )
    backwards = _head(
        draw(
            NumberLineFigure(alt=ALT, start=0, end=10, step=1, jumps=({"start": 6, "end": 2},)),
            "nb",
        )
    )
    # The arrow's wings sit behind its tip, so they trail in opposite directions.
    assert (forwards[0] < forwards[2]) != (backwards[0] < backwards[2])


def test_a_step_that_does_not_divide_the_line_is_refused() -> None:
    with pytest.raises(ValidationError):
        NumberLineFigure(alt=ALT, start=0, end=10, step=3)


def test_a_mark_off_the_end_of_the_line_is_refused() -> None:
    with pytest.raises(ValidationError):
        NumberLineFigure(alt=ALT, start=0, end=10, step=1, marks=({"at": 11},))


def test_a_line_too_long_to_read_is_refused() -> None:
    with pytest.raises(ValidationError):
        NumberLineFigure(alt=ALT, start=0, end=1000, step=1)


def test_decimal_ticks_are_written_the_norwegian_way() -> None:
    drawing = draw(NumberLineFigure(alt=ALT, start=0, end=2, step=0.5), "nb")
    assert [label.text for label in drawing.labels] == ["0", "0,5", "1", "1,5", "2"]


# --- boxes -------------------------------------------------------------------


def box(length: float, width: float, height: float, **labels) -> BoxFigure:
    return BoxFigure(alt=ALT, length=length, width=width, height=height, **labels)


def test_a_box_is_three_visible_faces_and_three_hidden_edges() -> None:
    drawing = draw(box(4, 3, 2), "nb")
    assert [path.role for path in drawing.paths] == ["outline"] * 3 + ["guide"] * 3
    # The hidden edges all start at the one corner nobody can see.
    starts = {tuple(_coordinates(path.d)[:2]) for path in drawing.paths[3:]}
    assert len(starts) == 1


def test_a_box_front_face_is_drawn_in_its_own_proportions() -> None:
    front = _coordinates(draw(box(4, 3, 2), "nb").paths[0].d)
    xs, ys = front[0::2], front[1::2]
    assert (max(xs) - min(xs)) / (max(ys) - min(ys)) == pytest.approx(2.0, abs=1e-3)


def test_a_cube_recedes_at_half_scale_and_45_degrees() -> None:
    drawing = draw(box(5, 5, 5), "nb")
    front = _coordinates(drawing.paths[0].d)
    side = max(front[0::2]) - min(front[0::2])
    top = _coordinates(drawing.paths[1].d)
    dx, dy = top[2] - top[0], top[3] - top[1]
    assert dx == pytest.approx(-dy, abs=0.02)
    assert math.hypot(dx, dy) == pytest.approx(side / 2, abs=0.05)


@pytest.mark.parametrize(
    ("length", "width", "height"), [(2, 12, 2), (12, 2, 2), (2, 2, 12), (5, 5, 5), (12, 12, 12)]
)
def test_a_box_and_its_longest_labels_stay_in_view_and_off_the_outline(
    length: float, width: float, height: float
) -> None:
    label = "x" * MAX_BOX_LABEL
    drawing = draw(
        box(length, width, height, length_label=label, width_label=label, height_label=label),
        "nb",
    )
    points = [c for path in drawing.paths for c in _coordinates(path.d)]
    xs, ys = points[0::2], points[1::2]
    assert all(0 <= x <= VIEW for x in xs) and all(0 <= y <= VIEW for y in ys)
    for placed in drawing.labels:
        span = _label_width(placed.text)
        low = {"start": placed.x, "end": placed.x - span, "middle": placed.x - span / 2}
        assert low[placed.anchor] >= 0 and low[placed.anchor] + span <= VIEW
    by_text = {placed.anchor: placed for placed in drawing.labels}
    assert by_text["end"].x < min(xs), "the height label sits left of the box"
    assert by_text["middle"].y > max(ys), "the length label sits below the box"

    # The width label sits below the receding bottom edge of the right face.
    # That edge rises to the right, so the label's left end is where it comes
    # closest; past the back corner there is no box above it at all.
    right_face = _coordinates(drawing.paths[2].d)
    (back_x, back_y), (front_x, front_y) = right_face[4:6], right_face[6:8]
    width_label = by_text["start"]
    top = width_label.y - width_label.size / 2
    if width_label.x < back_x:
        edge_y = front_y + (width_label.x - front_x) * (back_y - front_y) / (back_x - front_x)
        assert top > edge_y, "the width label sits clear of the right face"


def test_the_longest_labels_leave_room_for_the_box() -> None:
    """The floor `MAX_BOX_LABEL` exists for: two side labels never crowd it out."""
    label = "x" * MAX_BOX_LABEL
    drawing = draw(box(5, 5, 5, width_label=label, height_label=label), "nb")
    xs = [c for path in drawing.paths for c in _coordinates(path.d)][0::2]
    assert max(xs) - min(xs) >= 60


def test_a_plank_is_not_a_box() -> None:
    with pytest.raises(ValidationError, match="plank"):
        box(20, 2, 2)


def test_a_box_label_too_long_to_fit_is_refused() -> None:
    with pytest.raises(ValidationError):
        box(4, 3, 2, height_label="x" * (MAX_BOX_LABEL + 1))


# --- cylinders ---------------------------------------------------------------


def cylinder(radius: float, height: float, **labels) -> CylinderFigure:
    return CylinderFigure(alt=ALT, radius=radius, height=height, **labels)


def test_a_cylinder_hides_only_the_back_of_its_base() -> None:
    drawing = draw(cylinder(5, 10), "nb")
    roles = [path.role for path in drawing.paths]
    assert roles == ["outline", "outline", "outline", "outline", "guide"]


@pytest.mark.parametrize(("radius", "height"), [(5, 10), (1, 6), (3, 1), (6, 2)])
def test_a_cylinder_is_drawn_in_its_own_proportions(radius: float, height: float) -> None:
    drawing = draw(cylinder(radius, height), "nb")
    west, top, _, bottom = _coordinates(drawing.paths[1].d)
    east = _coordinates(drawing.paths[2].d)[0]
    # Coordinates are written to two decimals, so a low cylinder's ratio holds
    # to about one part in a thousand.
    assert (east - west) / (bottom - top) == pytest.approx(2 * radius / height, rel=1e-3)


@pytest.mark.parametrize(("radius", "height"), [(1, 6), (3, 1), (5, 10)])
def test_a_cylinder_and_its_longest_labels_stay_in_view(radius: float, height: float) -> None:
    label = "x" * MAX_BOX_LABEL
    drawing = draw(cylinder(radius, height, radius_label=label, height_label=label), "nb")
    west = _coordinates(drawing.paths[1].d)[0]
    for placed in drawing.labels:
        span = _label_width(placed.text)
        low = {"end": placed.x - span, "middle": placed.x - span / 2}[placed.anchor]
        assert low >= 0 and low + span <= VIEW
        assert placed.y - LABEL_SIZE / 2 >= 0
    height_label = next(p for p in drawing.labels if p.anchor == "end")
    assert height_label.x < west


def test_the_radius_runs_from_the_centre_and_the_diameter_across() -> None:
    radius = draw(cylinder(5, 10, radius_label="5 cm"), "nb")
    diameter = draw(cylinder(5, 10, diameter_label="10 cm"), "nb")
    west = _coordinates(radius.paths[1].d)[0]
    east = _coordinates(radius.paths[2].d)[0]
    assert _coordinates(radius.paths[-1].d)[0] == pytest.approx((west + east) / 2, abs=0.01)
    assert _coordinates(diameter.paths[-1].d)[0] == pytest.approx(west, abs=0.01)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"radius": 1, "height": 20}, "pipe"),
        ({"radius": 10, "height": 2}, "coin"),
        ({"radius": 5, "height": 10, "radius_label": "5", "diameter_label": "10"}, "not both"),
    ],
)
def test_a_cylinder_that_cannot_be_drawn_is_refused(fields: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CylinderFigure(alt=ALT, **fields)


# --- helpers -----------------------------------------------------------------


def _coordinates(d: str) -> list[float]:
    import re

    return [float(token) for token in re.findall(r"-?\d+\.?\d*", d)]


def _width(paths: list) -> float:
    xs = [x for path in paths for x in _coordinates(path.d)[0::2]]
    return max(xs) - min(xs)


def _head(drawing) -> list[float]:
    path = next(p for p in drawing.paths if p.role == "jump-head")
    return _coordinates(path.d)


def test_a_value_and_its_place_on_the_line_are_inverses() -> None:
    """The browser answers in pixels and the server grades in numbers.

    `line_x` is what draws the ticks and `line_value` is what the pointer
    handler undoes, so a drift between them puts the marker somewhere other than
    where the pupil let go.
    """
    figure = NumberLineFigure(alt=ALT, start=0, end=50, step=5)
    for value in (0, 17.5, 35, 50):
        assert line_value(figure, line_x(figure, value)) == pytest.approx(value)


def test_the_line_spans_the_drawing_between_its_margins() -> None:
    figure = NumberLineFigure(alt=ALT, start=10, end=20, step=1)
    assert line_x(figure, 10) == pytest.approx(PAD)
    assert line_x(figure, 20) == pytest.approx(VIEW - PAD)


def test_a_tick_index_refuses_what_falls_between_two() -> None:
    figure = NumberLineFigure(alt=ALT, start=0, end=50, step=5)
    assert tick_index(figure, 35) == 7
    assert tick_index(figure, 34) is None
    assert tick_index(figure, 55) is None


def test_tick_indices_hold_for_a_step_that_is_not_exact_in_binary() -> None:
    figure = NumberLineFigure(alt=ALT, start=0, end=1, step=0.1)
    assert [tick_index(figure, i * 0.1) for i in range(11)] == list(range(11))


def test_the_geometry_handed_to_the_browser_matches_the_drawing() -> None:
    """The script is given these rather than a second copy of the constants."""
    figure = NumberLineFigure(alt=ALT, start=0, end=10, step=1)
    geometry = line_geometry(figure)
    assert geometry["left"] == line_x(figure, 0)
    assert geometry["right"] == line_x(figure, 10)

    # A line with jumps sits lower, and the marker has to sit on it, not above.
    jumped = NumberLineFigure(alt=ALT, start=0, end=10, step=1, jumps=({"start": 2, "end": 6},))
    axis = next(p for p in draw(jumped, "nb").paths if p.role == "axis")
    assert f"{line_geometry(jumped)['y']:.2f}" in axis.d
