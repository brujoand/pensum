"""What every hands-on primitive shares: a board, a state, and one grading rule.

A primitive in `docs/design/activities.md` is a piece of interaction code with
its own tests, keyboard model and no-JavaScript fallback. Most of that is
different per primitive -- ten-frame cells are not base-ten rods -- but three
things are the same for all of them, and are here so no primitive can get them
subtly wrong on its own:

  * **The board is declared, not drawn.** `ActivityConfig.board` turns a state
    into a `Board`: the static strokes of a mat or a frame, the drop zones a
    pupil can tap, and one `Piece` for every object that *could* be on it,
    marked shown or not. The browser never computes where a counter goes; it
    only shows and hides pieces the server already placed, which is what makes
    snapping free and keeps the geometry in one language.

  * **The answer is one serialised state.** The page writes a JSON object into a
    single hidden `response` field, the same field every other item kind
    answers through, so the quiz routes, the session store and scoring need to
    know nothing about manipulatives. `read` parses it against this config's
    own limits and returns None for anything malformed, out of range or not
    reachable from the start; grading treats None as wrong and never raises.

  * **Without JavaScript the same target is asked as a number.** Every config
    names a numeric `fallback_answer` and the question it answers, and a typed
    number arriving in `response` is graded against it. That is the no-script
    road, and it is a real question rather than an error page (principle 12).

Nothing here is timed and nothing records process. Grading is a pure function of
the config and the final state (architecture.md, "Grading is a function of final
state").
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label, Path
from pensum.items.text import AuthoredText

Stage = Literal["concrete", "pictorial", "abstract"]


@dataclass(frozen=True)
class Piece:
    """One object a pupil can place, move or take away.

    Drawn whether or not it is on the board at the moment, because the browser
    shows and hides pieces rather than creating them. `zone` and `index` are the
    piece's address: which container it belongs to, and where it sits in that
    container's fill order. `row` and `col` are for the grid primitives, whose
    pieces are addressed in two dimensions.

    `shape` becomes a class name, the same way a figure's `role` does, so the
    stylesheet decides what a rod looks like and no colour is ever in the markup.
    """

    zone: str
    index: int
    shape: str
    x: float
    y: float
    w: float
    h: float
    shown: bool = True
    # Extra strokes drawn inside the piece: the ten segments of a rod, the grid
    # of a flat. Part of the piece so they show and hide with it.
    detail: str = ""
    label: str = ""
    row: int = 0
    col: int = 0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass(frozen=True)
class Zone:
    """A place a piece can be dropped, or tapped to add one."""

    name: str
    x: float
    y: float
    w: float
    h: float
    index: int = -1
    role: str = "zone"


@dataclass(frozen=True)
class Layer:
    """A group of the board that moves together, such as one pan of a balance.

    Most boards have a single layer. The balance has three, because a pan and
    everything in it tilts as one, and the stylesheet can only move a group.
    """

    role: str = "base"
    paths: tuple[Path, ...] = ()
    zones: tuple[Zone, ...] = ()
    pieces: tuple[Piece, ...] = ()
    labels: tuple[Label, ...] = ()
    # An SVG transform for the whole group: how a tipped balance is drawn.
    transform: str = ""


@dataclass(frozen=True)
class Board:
    """A primitive's picture, resolved for one state."""

    width: float
    height: float
    alt: str
    layers: tuple[Layer, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Comparison:
    """What the pupil built next to what was asked (activity rule 7).

    `made` and `asked` are the literal sentence halves; the boards are the same
    two things drawn, so the feedback shows before it says. A typed answer from
    the no-script road may have no board of its own.
    """

    sentence: str
    made: str
    asked: str
    made_board: Board | None
    asked_board: Board | None


class Fallback(BaseModel):
    """The question asked instead when the page runs no script.

    Optional: every primitive has a sensible default. An author overrides it when
    the default would be trivially answered by the prompt, as "how many dots?"
    is on a make-ten frame that says it wants ten.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: AuthoredText
    answer: float


class ActivityConfig(BaseModel):
    """The declared half of a primitive: its parameters and its rules.

    Subclasses add the parameters (`target`, `groups`, `accept` ...) and fill in
    the methods below. `extra="forbid"` because a misspelt `targte: 34` would
    otherwise be dropped in silence and the item would test the default.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The i18n key of the default no-script question. A class attribute, not a
    # field: it is the primitive's wording, not the author's.
    FALLBACK_KEY: ClassVar[str] = ""
    State: ClassVar[type[BaseModel]]

    kind: str
    alt: AuthoredText
    fallback: Fallback | None = None

    # --- what a subclass provides -----------------------------------------

    def initial(self) -> BaseModel:
        """The state the board opens in."""
        raise NotImplementedError

    def solution(self) -> BaseModel:
        """One state that is right. Drawn in feedback as "what was asked"."""
        raise NotImplementedError

    def admits(self, state: Any) -> bool:
        """Whether a state could have come off this board at all."""
        raise NotImplementedError

    def grade_state(self, state: Any) -> bool:
        raise NotImplementedError

    def default_fallback(self) -> float:
        raise NotImplementedError

    def from_number(self, value: float) -> BaseModel | None:
        """A typed number drawn as a board state, if it has an obvious one."""
        return None

    def board(self, state: Any, locale: str) -> Board:
        raise NotImplementedError

    def describe(self, state: Any, locale: str) -> str:
        """The state in words, literally: "34 (3 tiere og 4 enere)"."""
        raise NotImplementedError

    def limits(self) -> dict[str, Any]:
        """The numbers the page's script needs to refuse an impossible move."""
        return {}

    def say(self, locale: str) -> dict[str, str]:
        """Sentence templates the page reads its live status from."""
        return {}

    def fallback_key(self) -> str:
        return self.FALLBACK_KEY

    # --- the no-script road -------------------------------------------------
    #
    # A number by default. The language primitives answer without a script by
    # typing a word or a sentence, or by picking one of a few, so these four
    # are where such a primitive says what its typed answer is. A primitive
    # that keeps the numeric road overrides none of them.

    def typed_right(self, text: str) -> bool:
        """Whether a no-script answer is right. Never raises."""
        value = parse_number(text)
        return value is not None and abs(value - self.fallback_answer()) < 1e-9

    def typed_example(self) -> str:
        """One right no-script answer, exactly as the form would send it."""
        return number_text(self.fallback_answer())

    def typed_compare(self, text: str, locale: str) -> Comparison | None:
        """The feedback for a typed answer, or None for the numeric default."""
        return None

    def made_key(self) -> str:
        """The i18n key of the sentence under a built answer's comparison."""
        return "activity.you_made"

    # --- shared ---------------------------------------------------------------

    def fallback_answer(self) -> float:
        return self.fallback.answer if self.fallback else self.default_fallback()

    def fallback_prompt(self, locale: str) -> str:
        if self.fallback:
            return self.fallback.prompt.get(locale)
        return translate(locale, self.fallback_key())

    def serialise(self, state: BaseModel) -> str:
        return json.dumps(state.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)

    def read(self, response: str) -> BaseModel | None:
        """Parse a submitted state, or None. Never raises.

        The response arrives from a form, so anything at all can be in it. Every
        way it can be wrong -- not JSON, not an object, a string where a count
        should be, a count the board has no room for -- ends in the same None,
        and None is graded wrong.
        """
        try:
            raw = json.loads(response)
        except (ValueError, RecursionError):
            return None
        if not isinstance(raw, dict):
            return None
        try:
            # Validated from the JSON text in strict mode: a count must be a
            # whole number, not "3" and not 3.0, and a list is a list.
            state = self.State.model_validate_json(response, strict=True)
        except (ValidationError, TypeError, ValueError):
            return None
        try:
            return state if self.admits(state) else None
        except (TypeError, ValueError, IndexError):
            return None

    @model_validator(mode="after")
    def _check_fallback(self) -> ActivityConfig:
        if self.fallback is not None and not math.isfinite(self.fallback.answer):
            raise ValueError("a fallback answer must be a number")
        return self


def parse_number(text: str) -> float | None:
    """A typed number, Norwegian comma or English point. None if it is not one."""
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def number_text(value: float) -> str:
    """7.0 as "7", 2.5 as "2,5": how a pupil writes it."""
    return str(int(value)) if float(value).is_integer() else str(value).replace(".", ",")


def grade(config: ActivityConfig, response: str) -> bool:
    """Right or wrong, from the final state or from the typed fallback."""
    text = response.strip()
    if not text:
        return False
    if text.startswith("{"):
        state = config.read(text)
        return state is not None and config.grade_state(state)
    return config.typed_right(text)


def compare(config: ActivityConfig, response: str, locale: str) -> Comparison:
    """Put what was built beside what was asked, in words and in pictures."""
    solution = config.solution()
    asked = config.describe(solution, locale)
    asked_board = config.board(solution, locale)
    text = response.strip()

    if text.startswith("{"):
        state = config.read(text)
        if state is not None:
            made = config.describe(state, locale)
            return Comparison(
                translate(locale, config.made_key(), made=made, asked=asked),
                made,
                asked,
                config.board(state, locale),
                asked_board,
            )
        # A state that did not parse cannot be drawn. Said plainly rather than
        # guessed at: the pupil did nothing wrong that they could fix.
        made = translate(locale, "activity.unreadable")
        return Comparison(made, made, asked, None, asked_board)

    typed = config.typed_compare(text, locale)
    if typed is not None:
        return typed

    # The no-script road: a typed number, compared with the number asked for.
    value = parse_number(text)
    made = number_text(value) if value is not None else (text or "—")
    wanted = number_text(config.fallback_answer())
    drawn = None
    if value is not None and config.fallback is None:
        state = config.from_number(value)
        drawn = config.board(state, locale) if state is not None else None
    return Comparison(
        translate(locale, "activity.you_wrote", made=made, asked=wanted),
        made,
        wanted,
        drawn,
        asked_board,
    )


def join_numbers(values: list[int] | tuple[int, ...], locale: str) -> str:
    """ "5, 4 og 3": a list the way it is said."""
    words = [str(v) for v in values]
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {translate(locale, 'activity.and')} {words[-1]}"


def plural(locale: str, key: str, count: int, **kwargs: Any) -> str:
    """`key_one` for exactly one, `key` otherwise: "1 brikke", "3 brikker"."""
    return translate(locale, f"{key}_one" if count == 1 else key, count=count, **kwargs)


def say_keys(locale: str, *keys: str) -> dict[str, str]:
    """Raw templates for the page script, keyed by their last segment."""
    return {key.rsplit(".", 1)[-1]: translate(locale, key) for key in keys}


NonNegative = Field(ge=0)
