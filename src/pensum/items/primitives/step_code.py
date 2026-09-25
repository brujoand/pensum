"""Step code: command tiles that move a robot through a grid.

*Robot path*, *Bug hunt* and *Blocks and text side by side* from
`docs/design/subjects/matematikk.md`, strand 10. A grid with a robot, some wall
squares and a goal; the pupil builds a program from tiles -- *step*, *turn
left*, *turn right*, and where the item allows them *repeat N* with a body and
*if wall ahead* with a body -- then presses Run to watch it, or steps through it
one move at a time. The primitive stays the same from 2. to 10. trinn; only the
tile set grows, and from 7. trinn the same program is shown beside the tiles as
Python-like text, generated from it and read-only.

**Graded by running it.** The submitted program is executed here, on the
declared grid, by the same rules the page's Run uses (`trace`): a step into a
wall or off the grid stops the robot, and the program is right when the robot
stands on the goal when it ends, never having hit anything, within the item's
`max_tiles` if it has one. There is no `while`, so every program ends, but a
repeat inside a repeat can still run for a long time; the executor counts every
command it carries out and stops at `STEP_LIMIT`, and a program that reaches it
is wrong rather than slow.

**The state is the program and a cursor.** The program is nested JSON, exactly
the shape the tiles build: `"step"`, `"left"`, `"right"`,
`{"repeat": 3, "do": [...]}`, `{"if_wall": [...]}`. The cursor is where the next
tile goes, as a path of indices into the nesting; it is part of the state only
so undo puts it back, and grading never reads it. A tile the item does not
offer, a repeat count it does not list, nesting deeper than `MAX_DEPTH` or more
than `MAX_TILES` tiles is a state no board produced, and is refused.

**The page never has the solution.** It needs the grid to run a program, and
the grid is the question. The declared `solution` is used for the feedback's
"what was asked" and for the no-script road only.

Without a script the pupil picks a program from three or four listed ones: the
solution and near misses made from it by one change each (a turn the wrong way,
a repeat one too many, the last tile dropped...), every near miss checked by
the executor to fail. The pick is graded by running the program picked, so a
near miss that happened to work would be right; the listing is in an order
that is stable per item and is not the order they were made in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label, Path
from pensum.items.primitives import tiles
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer, Piece, plural

MAX_TILES = 30
MAX_DEPTH = 3
MAX_SIDE = 8
STEP_LIMIT = 400

CELL = 40.0
MARGIN = 12.0
BOT = 26.0
TRAIL = 8.0
# Room for the line under the grid that says which mark is which.
LEGEND_W = 290.0

Facing = Literal["up", "right", "down", "left"]
FACINGS: tuple[str, ...] = ("up", "right", "down", "left")
DX = (0, 1, 0, -1)
DY = (-1, 0, 1, 0)
Tile = Literal["step", "left", "right", "repeat", "if_wall"]
Simple = Literal["step", "left", "right"]


class Repeat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    repeat: int = Field(ge=2, le=9)
    do: tuple[Command, ...] = ()


class IfWall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    if_wall: tuple[Command, ...] = ()


Command = Union[Simple, Repeat, IfWall]  # noqa: UP007
Repeat.model_rebuild()
IfWall.model_rebuild()


class Start(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    facing: Facing = "right"


class StepCodeState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    program: tuple[Command, ...] = ()
    cursor: tuple[int, ...] = (0,)


@dataclass(frozen=True)
class Trace:
    """What running a program did: every pose from the start, and how it ended.

    `outcome` is `goal` (stands on it at the end), `short` (ended somewhere
    else), `wall` (stepped into a wall or off the grid, and stopped) or `limit`
    (ran `STEP_LIMIT` commands without ending).
    """

    poses: tuple[tuple[int, int, int], ...]
    outcome: Literal["goal", "short", "wall", "limit"]


class StepCodeActivity(ActivityConfig):
    """Move the robot from `start` to `goal` with a program of tiles."""

    FALLBACK_KEY = "activity.step_code.ask"
    State = StepCodeState

    kind: Literal["step_code"] = "step_code"
    width: int = Field(ge=2, le=MAX_SIDE)
    height: int = Field(ge=1, le=MAX_SIDE)
    start: Start
    goal: tuple[int, int]
    walls: tuple[tuple[int, int], ...] = ()
    tiles: tuple[Tile, ...] = ("step", "left", "right")
    repeats: tuple[int, ...] = (2, 3, 4)
    max_tiles: int | None = Field(default=None, ge=1, le=MAX_TILES)
    # The program the board opens with: a bug hunt starts from one that almost
    # works. Empty for a program built from nothing.
    begin: tuple[Command, ...] = ()
    solution_program: tuple[Command, ...] = Field(alias="solution")
    # Show the program as Python-like text beside the tiles (7. trinn and up).
    text: bool = False

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _check(self) -> StepCodeActivity:
        if self.fallback is not None:
            raise ValueError("step_code asks for a program without a script, picked from a list")
        cells = [(self.start.x, self.start.y), self.goal, *self.walls]
        for x, y in cells:
            if not (0 <= x < self.width and 0 <= y < self.height):
                raise ValueError(f"({x}, {y}) is off the {self.width} by {self.height} grid")
        if (self.start.x, self.start.y) in self.walls or self.goal in self.walls:
            raise ValueError("the robot and the goal stand on open squares")
        if (self.start.x, self.start.y) == self.goal:
            raise ValueError("the robot starts on the goal")
        if "step" not in self.tiles:
            raise ValueError("a robot needs at least the step tile")
        if any(not 2 <= n <= 9 for n in self.repeats):
            raise ValueError("a repeat count is from 2 to 9")
        for name, program in (("begin", self.begin), ("solution", self.solution_program)):
            if not self.allowed(program):
                raise ValueError(f"{name} uses a tile or a count the item does not offer")
        if len(self.near_misses()) < 2:
            raise ValueError("fewer than two near misses fail, so there is nothing to pick from")
        return self

    # --- the program -------------------------------------------------------------

    def allowed(self, program: tuple[Command, ...], depth: int = 1) -> bool:
        """Whether a program uses only this item's tiles, counts and depth.

        A block may stand at depth 1 or 2, so a body is never deeper than
        `MAX_DEPTH`, which is also the longest a cursor can be.
        """
        for command in program:
            if isinstance(command, str):
                if command not in self.tiles:
                    return False
            elif isinstance(command, Repeat):
                if "repeat" not in self.tiles or command.repeat not in self.repeats:
                    return False
                if depth >= MAX_DEPTH or not self.allowed(command.do, depth + 1):
                    return False
            elif isinstance(command, IfWall):
                if "if_wall" not in self.tiles:
                    return False
                if depth >= MAX_DEPTH or not self.allowed(command.if_wall, depth + 1):
                    return False
            else:
                return False
        return count(program) <= MAX_TILES

    def blocked(self, x: int, y: int) -> bool:
        return not (0 <= x < self.width and 0 <= y < self.height) or (x, y) in self.walls

    def trace(self, program: tuple[Command, ...]) -> Trace:
        """Run a program on the declared grid; the same rules as `stepCodeTrace`."""
        facing = FACINGS.index(self.start.facing)
        pose = (self.start.x, self.start.y, facing)
        poses = [pose]
        budget = [STEP_LIMIT]

        def run(body: tuple[Command, ...]) -> str | None:
            nonlocal pose
            for command in body:
                budget[0] -= 1
                if budget[0] < 0:
                    return "limit"
                x, y, f = pose
                if command == "step":
                    nx, ny = x + DX[f], y + DY[f]
                    if self.blocked(nx, ny):
                        return "wall"
                    pose = (nx, ny, f)
                    poses.append(pose)
                elif command == "left":
                    pose = (x, y, (f + 3) % 4)
                    poses.append(pose)
                elif command == "right":
                    pose = (x, y, (f + 1) % 4)
                    poses.append(pose)
                elif isinstance(command, Repeat):
                    for _ in range(command.repeat):
                        stop = run(command.do)
                        if stop:
                            return stop
                        budget[0] -= 1
                        if budget[0] < 0:
                            return "limit"
                elif isinstance(command, IfWall):
                    if self.blocked(x + DX[f], y + DY[f]):
                        stop = run(command.if_wall)
                        if stop:
                            return stop
            return None

        stop = run(program)
        if stop is not None:
            return Trace(tuple(poses), stop)  # type: ignore[arg-type]
        x, y, _ = pose
        return Trace(tuple(poses), "goal" if (x, y) == self.goal else "short")

    def works(self, program: tuple[Command, ...]) -> bool:
        if self.trace(program).outcome != "goal":
            return False
        return self.max_tiles is None or count(program) <= self.max_tiles

    # --- rules -----------------------------------------------------------------

    def initial(self) -> StepCodeState:
        return StepCodeState(program=self.begin, cursor=(len(self.begin),))

    def solution(self) -> StepCodeState:
        program = self.solution_program
        return StepCodeState(program=program, cursor=(len(program),))

    def admits(self, state: StepCodeState) -> bool:
        return self.allowed(state.program) and valid_cursor(state.program, state.cursor)

    def grade_state(self, state: StepCodeState) -> bool:
        return self.works(state.program)

    def default_fallback(self) -> float:
        return 0.0

    def describe(self, state: StepCodeState, locale: str) -> str:
        n = count(state.program)
        if not n:
            return translate(locale, "activity.step_code.empty")
        return plural(locale, "activity.step_code.made", n, tiles=words(state.program, locale))

    def made_key(self) -> str:
        return "activity.step_code.you_made"

    def limits(self) -> dict[str, Any]:
        # The grid, which is the question, and the tile rules. Never the
        # solution: the module docstring says what uses it.
        return {
            "width": self.width,
            "height": self.height,
            "start": [self.start.x, self.start.y, FACINGS.index(self.start.facing)],
            "goal": list(self.goal),
            "walls": [list(w) for w in self.walls],
            "tiles": list(self.tiles),
            "repeats": list(self.repeats),
            "max": MAX_TILES,
            "depth": MAX_DEPTH,
            "limit": STEP_LIMIT,
            "text": self.text,
        }

    def say(self, locale: str) -> dict[str, Any]:
        keys = (
            "empty", "made", "made_one", "step", "left", "right", "repeat", "if_wall",
            "block", "end", "start_line", "cursor", "py_step", "py_left", "py_right",
            "py_repeat", "py_if", "py_pass", "run_goal", "run_short", "run_wall", "run_limit",
        )  # fmt: skip
        out: dict[str, Any] = {k: translate(locale, f"activity.step_code.{k}") for k in keys}
        out["and"] = translate(locale, "activity.and")
        return out

    def listing(self, program: tuple[Command, ...], locale: str) -> str:
        """The program as the page lists it: text for the items that show text,
        indented tile words for the rest."""
        return as_text(program, locale) if self.text else as_lines(program, locale)

    # --- the no-script road ----------------------------------------------------

    def near_misses(self) -> list[tuple[Command, ...]]:
        """Programs one change away from the solution that fail, first three."""
        right = self.solution_program
        found: list[tuple[Command, ...]] = []
        for candidate in _mutations(right, self.repeats):
            if candidate == right or candidate in found or not candidate:
                continue
            if not self.allowed(candidate) or self.works(candidate):
                continue
            found.append(candidate)
            if len(found) == 3:
                break
        return found

    def options(self) -> list[tuple[Command, ...]]:
        """The solution and its near misses, in the order the page lists them."""
        programs = [self.solution_program, *self.near_misses()]
        return sorted(programs, key=lambda p: tiles.mix(self.serialise_program(p)))

    def serialise_program(self, program: tuple[Command, ...]) -> str:
        return self.serialise(StepCodeState(program=program))

    def _picked(self, text: str) -> tuple[Command, ...] | None:
        value = text.strip()
        if not value or len(value) > 1 or value not in "123456789":
            return None
        index = int(value) - 1
        options = self.options()
        return options[index] if index < len(options) else None

    def typed_right(self, text: str) -> bool:
        picked = self._picked(text)
        return picked is not None and self.works(picked)

    def typed_example(self) -> str:
        return str(self.options().index(self.solution_program) + 1)

    def typed_compare(self, text: str, locale: str) -> Comparison:
        picked = self._picked(text)
        right = self.solution()
        asked = self.describe(right, locale)
        if picked is None:
            made = text.strip() or "—"
            drawn = None
        else:
            state = StepCodeState(program=picked, cursor=(len(picked),))
            made = self.describe(state, locale)
            drawn = self.outcome_board(state, locale)
        return Comparison(
            translate(locale, self.made_key(), made=made, asked=asked),
            made,
            asked,
            drawn,
            self.outcome_board(right, locale),
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: StepCodeState, locale: str) -> Board:
        """The grid with the robot at the start: the page's Run moves it."""
        start = (self.start.x, self.start.y, FACINGS.index(self.start.facing))
        return self._draw(start, (), locale)

    def outcome_board(self, state: StepCodeState, locale: str) -> Board:
        """The grid after the program has run: the trail, and where it stopped."""
        poses = self.trace(state.program).poses
        return self._draw(poses[-1], tuple((x, y) for x, y, _ in poses), locale)

    def _draw(
        self, pose: tuple[int, int, int], trail: tuple[tuple[int, int], ...], locale: str
    ) -> Board:
        w, h = self.width, self.height
        left, top = MARGIN, MARGIN
        grid = " ".join(
            [f"M{left:.1f},{top + r * CELL:.1f} h{w * CELL:.1f}" for r in range(h + 1)]
            + [f"M{left + c * CELL:.1f},{top:.1f} v{h * CELL:.1f}" for c in range(w + 1)]
        )
        paths = [Path(grid, "code-grid")]
        for x, y in self.walls:
            cx, cy = left + x * CELL, top + y * CELL
            paths.append(
                Path(f"M{cx:.1f},{cy:.1f} h{CELL:.1f} v{CELL:.1f} h{-CELL:.1f} Z", "code-wall")
            )
            paths.append(
                Path(
                    " ".join(
                        f"M{cx + i * CELL / 4:.1f},{cy + CELL:.1f} L{cx + CELL:.1f},{cy + i * CELL / 4:.1f}"
                        for i in range(4)
                    ),
                    "code-wall-hatch",
                )
            )
        gx, gy = left + (self.goal[0] + 0.5) * CELL, top + (self.goal[1] + 0.5) * CELL
        paths.append(Path(_ring(gx, gy, 15) + " " + _ring(gx, gy, 8), "code-goal"))

        pieces: list[Piece] = []
        visited = set(trail)
        for y in range(h):
            for x in range(w):
                cell = y * w + x
                px, py = left + x * CELL, top + y * CELL
                pieces.append(
                    Piece(
                        "trail",
                        cell,
                        "trail",
                        px + (CELL - TRAIL) / 2,
                        py + (CELL - TRAIL) / 2,
                        TRAIL,
                        TRAIL,
                        shown=(x, y) in visited,
                    )
                )
        for y in range(h):
            for x in range(w):
                for f in range(4):
                    px, py = left + x * CELL + (CELL - BOT) / 2, top + y * CELL + (CELL - BOT) / 2
                    pieces.append(
                        Piece(
                            "bot",
                            (y * w + x) * 4 + f,
                            "bot",
                            px,
                            py,
                            BOT,
                            BOT,
                            shown=pose == (x, y, f),
                            detail=_arrow(px + BOT / 2, py + BOT / 2, f),
                        )
                    )
        legend = Label(
            left,
            top + h * CELL + 14,
            translate(locale, "activity.step_code.legend"),
            size=11,
            anchor="start",
        )
        return Board(
            max(w * CELL, LEGEND_W) + 2 * MARGIN,
            h * CELL + 2 * MARGIN + 16,
            self.alt.get(locale),
            (Layer("base", tuple(paths), (), tuple(pieces), (legend,)),),
        )


# --- programs, as data -------------------------------------------------------------


def count(program: tuple[Command, ...]) -> int:
    """Tiles in a program, a block and everything in it included."""
    total = 0
    for command in program:
        total += 1
        if isinstance(command, Repeat):
            total += count(command.do)
        elif isinstance(command, IfWall):
            total += count(command.if_wall)
    return total


def body(command: Command) -> tuple[Command, ...] | None:
    if isinstance(command, Repeat):
        return command.do
    if isinstance(command, IfWall):
        return command.if_wall
    return None


def valid_cursor(program: tuple[Command, ...], cursor: tuple[int, ...]) -> bool:
    """A path of block indices ending in a place in the innermost body."""
    if not cursor or len(cursor) > MAX_DEPTH:
        return False
    here: tuple[Command, ...] | None = program
    for index in cursor[:-1]:
        if here is None or not 0 <= index < len(here):
            return False
        here = body(here[index])
    return here is not None and 0 <= cursor[-1] <= len(here)


def words(program: tuple[Command, ...], locale: str) -> str:
    """ "gå fram, gjenta 3 ganger (gå fram, snu mot høyre)": said in one line."""
    parts = []
    for command in program:
        if isinstance(command, str):
            parts.append(translate(locale, f"activity.step_code.{command}"))
        else:
            head = (
                translate(locale, "activity.step_code.repeat", n=command.repeat)
                if isinstance(command, Repeat)
                else translate(locale, "activity.step_code.if_wall")
            )
            inner = body(command) or ()
            parts.append(
                translate(
                    locale,
                    "activity.step_code.block",
                    head=head,
                    body=words(inner, locale) if inner else "—",
                )
            )
    return ", ".join(parts)


def as_lines(program: tuple[Command, ...], locale: str, depth: int = 0) -> str:
    """The program as tile words, one per line, a block's body indented."""
    lines = []
    pad = "    " * depth
    for command in program:
        if isinstance(command, str):
            lines.append(pad + translate(locale, f"activity.step_code.{command}"))
            continue
        if isinstance(command, Repeat):
            lines.append(pad + translate(locale, "activity.step_code.repeat", n=command.repeat))
        else:
            lines.append(pad + translate(locale, "activity.step_code.if_wall"))
        inner = body(command) or ()
        if inner:
            lines.append(as_lines(inner, locale, depth + 1))
        lines.append(pad + translate(locale, "activity.step_code.end"))
    return "\n".join(lines)


def as_text(program: tuple[Command, ...], locale: str, depth: int = 0) -> str:
    """The program as Python-like text; `stepCodeText` in the page is the same."""
    lines = []
    pad = "    " * depth
    for command in program:
        if isinstance(command, str):
            lines.append(pad + translate(locale, f"activity.step_code.py_{command}"))
            continue
        if isinstance(command, Repeat):
            lines.append(pad + translate(locale, "activity.step_code.py_repeat", n=command.repeat))
        else:
            lines.append(pad + translate(locale, "activity.step_code.py_if"))
        inner = body(command) or ()
        lines.append(
            as_text(inner, locale, depth + 1)
            if inner
            else "    " * (depth + 1) + translate(locale, "activity.step_code.py_pass")
        )
    return "\n".join(lines)


def _mutations(program: tuple[Command, ...], repeats: tuple[int, ...]) -> list[tuple[Command, ...]]:
    """One-change variants of a program, the kinds of slip a pupil makes, most
    telling first: a turn the wrong way, a repeat count off by one, the last
    tile dropped, one step too many, the first step left out."""
    out: list[tuple[Command, ...]] = []
    swap = {"left": "right", "right": "left"}

    def turned(p: tuple[Command, ...]) -> tuple[Command, ...] | None:
        for i, c in enumerate(p):
            if isinstance(c, str) and c in swap:
                return (*p[:i], swap[c], *p[i + 1 :])  # type: ignore[return-value]
            inner = body(c)
            if inner:
                changed = turned(inner)
                if changed is not None:
                    return (*p[:i], _with_body(c, changed), *p[i + 1 :])
        return None

    def recount(p: tuple[Command, ...], delta: int) -> tuple[Command, ...] | None:
        for i, c in enumerate(p):
            if isinstance(c, Repeat) and c.repeat + delta in repeats:
                return (*p[:i], Repeat(repeat=c.repeat + delta, do=c.do), *p[i + 1 :])
        return None

    for candidate in (
        turned(program),
        recount(program, 1),
        recount(program, -1),
        program[:-1],
        (*program, "step"),
        _drop_first_step(program),
    ):
        if candidate is not None:
            out.append(candidate)
    return out


def _drop_first_step(p: tuple[Command, ...]) -> tuple[Command, ...] | None:
    for i, c in enumerate(p):
        if c == "step":
            return (*p[:i], *p[i + 1 :])
    return None


def _with_body(command: Command, inner: tuple[Command, ...]) -> Command:
    if isinstance(command, Repeat):
        return Repeat(repeat=command.repeat, do=inner)
    return IfWall(if_wall=inner)


def _ring(cx: float, cy: float, r: float) -> str:
    return (
        f"M{cx - r:.1f},{cy:.1f} a{r:.1f},{r:.1f} 0 1,0 {2 * r:.1f},0 "
        f"a{r:.1f},{r:.1f} 0 1,0 {-2 * r:.1f},0"
    )


def _arrow(cx: float, cy: float, facing: int) -> str:
    """A triangle inside the robot pointing the way it faces."""
    tip, side = 8.0, 6.0
    dx, dy = DX[facing], DY[facing]
    # Perpendicular to the facing.
    px, py = -dy, dx
    ax, ay = cx + dx * tip, cy + dy * tip
    bx, by = cx - dx * side + px * side, cy - dy * side + py * side
    ex, ey = cx - dx * side - px * side, cy - dy * side - py * side
    return f"M{ax:.1f},{ay:.1f} L{bx:.1f},{by:.1f} L{ex:.1f},{ey:.1f} Z"


__all__ = [
    "MAX_DEPTH",
    "MAX_TILES",
    "STEP_LIMIT",
    "IfWall",
    "Repeat",
    "StepCodeActivity",
    "StepCodeState",
    "Trace",
    "as_text",
    "count",
    "valid_cursor",
]
