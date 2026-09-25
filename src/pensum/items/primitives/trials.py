"""Trials: say what you expect, then spin a spinner or roll dice and watch.

*Spin 100 times* from `docs/design/subjects/matematikk.md`, strand 9. The pupil
first records a prediction -- which outcome comes up most often, or about how
many times out of a hundred one outcome comes up, picked from a few declared
bands -- and it is locked. Then they run 1, 10 or 100 trials at a time and
watch the tally fill, as bars and as numbers.

**Graded on the prediction, never on the draws.** Chance is exactly the topic
where a right answer can be followed by a surprising tally, and a pupil who
reasoned well must not be marked wrong by a streak of luck. So the answer is
the reasoning target, worked out here from what the item declares and never
authored as a letter: the outcome with the biggest share (or *all equally
likely* when every share is the same), or the band that holds the expected
count. A spinner whose largest sectors tie, or bands where the expected count
falls in none or in two, is a typo and fails when the item loads.

**The draws happen in the browser, and the server can check them.** Every
showing of the question is issued a fresh seed (`opening`), which travels in
the state with the number of trials run and the tally. The generator is
xorshift32 here and in `trials.js`, so the server replays the seed and refuses
a tally the page could not have produced -- a state no board produced is
malformed, as everywhere else. Grading reads the prediction alone.

**Locked means locked.** Once one trial has run the prediction cannot change,
and the page's undo cannot go back across that step either (`sealed` in
`core.js`), because an undo that reopened the prediction would let it be
written after the result was seen.

**Nothing on the page says what to expect.** The page is sent the sector sizes,
which the spinner shows anyway because they are the question, and never an
expected count or which choice is right. Tallies fill without animation, one
batch at a time, whatever the comfort setting.

Without a script there are no trials to run: the prediction is asked as radio
buttons under the same picture, and graded the same way.
"""

from __future__ import annotations

import math
import secrets
from fractions import Fraction
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label, Path
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer, Piece, plural
from pensum.items.text import AuthoredText

# The most trials one showing may run: "repeat with 1000", and no further.
MAX_TRIALS = 1000
RUNS = (1, 10, 100)
SEED_MAX = 2**31 - 1
EQUAL = "equal"
# Bars are drawn in steps of one twentieth of all trials so far: pre-rendered,
# shown and hidden like every other piece.
LEVELS = 20

MARGIN = 12.0
RADIUS = 64.0
DIE = 44.0
BAR_W = 22.0
BAR_GAP = 6.0
BAR_H = 100.0


class Sector(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z_]{0,15}$")
    label: AuthoredText
    # Relative size: a sector of 2 is twice a sector of 1.
    size: int = Field(ge=1, le=12)


class TrialsState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction: str | None = None
    seed: int = Field(default=1, ge=1, le=SEED_MAX)
    done: int = Field(default=0, ge=0, le=MAX_TRIALS)
    tally: tuple[int, ...] = ()


class TrialsActivity(ActivityConfig):
    """Predict, then run trials on a declared spinner or dice."""

    FALLBACK_KEY = "activity.trials.ask_most"
    State = TrialsState

    kind: Literal["trials"] = "trials"
    spinner: tuple[Sector, ...] | None = Field(default=None, min_length=2, max_length=6)
    dice: Literal[1, 2] | None = None
    question: Literal["most", "count"] = "most"
    # For `count`: which outcome, out of how many trials, in which bands.
    outcome: str | None = None
    of: int = Field(default=100, ge=10, le=MAX_TRIALS)
    bands: tuple[tuple[int, int], ...] = ()

    @model_validator(mode="after")
    def _check(self) -> TrialsActivity:
        if (self.spinner is None) == (self.dice is None):
            raise ValueError("trials use either a spinner or dice")
        if self.fallback is not None:
            raise ValueError("trials ask the prediction without a script")
        ids = [o[0] for o in self.outcomes()]
        if len(set(ids)) != len(ids):
            raise ValueError("two sectors share an id")
        if EQUAL in ids:
            raise ValueError(f"{EQUAL!r} is the choice for all equally likely, not a sector")
        if self.question == "most":
            if self.outcome is not None or self.bands:
                raise ValueError("outcome and bands are for a count question")
            top = max(self.weights())
            winners = [w for w in self.weights() if w == top]
            if 1 < len(winners) < len(self.weights()):
                raise ValueError("the largest shares tie, so no one outcome comes up most")
        else:
            if self.outcome not in ids:
                raise ValueError(f"a count question needs an outcome among {ids}")
            if not 2 <= len(self.bands) <= 5:
                raise ValueError("a count question offers two to five bands")
            last = -1
            for lo, hi in self.bands:
                if not last < lo <= hi <= self.of:
                    raise ValueError("bands go up in order, do not overlap, and stay within of")
                last = hi
            if sum(1 for lo, hi in self.bands if lo <= self.expected() <= hi) != 1:
                raise ValueError("the expected count must fall in exactly one band")
        return self

    # --- the model -------------------------------------------------------------

    def outcomes(self) -> list[tuple[str, AuthoredText | str, int]]:
        """(id, label, weight) for every outcome, in the order they are drawn."""
        if self.spinner is not None:
            return [(s.id, s.label, s.size) for s in self.spinner]
        if self.dice == 1:
            return [(str(n), str(n), 1) for n in range(1, 7)]
        return [(str(n), str(n), 6 - abs(n - 7)) for n in range(2, 13)]

    def weights(self) -> list[int]:
        return [w for _, _, w in self.outcomes()]

    def label(self, outcome: int, locale: str) -> str:
        text = self.outcomes()[outcome][1]
        return text if isinstance(text, str) else text.get(locale)

    def expected(self) -> Fraction:
        """How many of `of` trials the outcome is expected to give."""
        index = [o[0] for o in self.outcomes()].index(self.outcome or "")
        return Fraction(self.of * self.weights()[index], sum(self.weights()))

    def choices(self) -> list[str]:
        """The ids a prediction can be, in the order the page offers them."""
        if self.question == "count":
            return [f"b{i}" for i in range(len(self.bands))]
        return [o[0] for o in self.outcomes()] + [EQUAL]

    def choice_text(self, choice: str, locale: str) -> str:
        if choice == EQUAL:
            return translate(locale, "activity.trials.equal")
        if self.question == "count":
            lo, hi = self.bands[int(choice[1:])]
            return translate(locale, "activity.trials.band", lo=lo, hi=hi)
        return self.label([o[0] for o in self.outcomes()].index(choice), locale)

    def right(self) -> str:
        """The reasoning target. Computed, never authored; see the docstring."""
        if self.question == "count":
            expected = self.expected()
            return next(f"b{i}" for i, (lo, hi) in enumerate(self.bands) if lo <= expected <= hi)
        weights = self.weights()
        if len(set(weights)) == 1:
            return EQUAL
        return self.outcomes()[weights.index(max(weights))][0]

    def simulate(self, seed: int, count: int) -> tuple[int, ...]:
        return simulate(seed, count, self.weights() if self.spinner else None, self.dice or 0)

    # --- rules -----------------------------------------------------------------

    def initial(self) -> TrialsState:
        return TrialsState(tally=(0,) * len(self.outcomes()))

    def opening(self) -> TrialsState:
        return TrialsState(seed=secrets.randbelow(SEED_MAX) + 1, tally=(0,) * len(self.outcomes()))

    def solution(self) -> TrialsState:
        return TrialsState(prediction=self.right(), tally=(0,) * len(self.outcomes()))

    def admits(self, state: TrialsState) -> bool:
        if state.prediction is not None and state.prediction not in self.choices():
            return False
        # Trials run only after a prediction: that is the lock.
        if state.done and state.prediction is None:
            return False
        if len(state.tally) != len(self.outcomes()):
            return False
        return state.tally == self.simulate(state.seed, state.done)

    def grade_state(self, state: TrialsState) -> bool:
        return state.prediction == self.right()

    def default_fallback(self) -> float:
        return 0.0

    def fallback_prompt(self, locale: str) -> str:
        if self.question == "count":
            index = [o[0] for o in self.outcomes()].index(self.outcome or "")
            return translate(
                locale,
                "activity.trials.ask_count",
                of=self.of,
                outcome=self.label(index, locale),
            )
        return translate(locale, self.FALLBACK_KEY)

    def describe(self, state: TrialsState, locale: str) -> str:
        if state.prediction is None:
            text = translate(locale, "activity.trials.none")
        else:
            text = translate(
                locale, "activity.trials.made", choice=self.choice_text(state.prediction, locale)
            )
        if state.done:
            counts = [
                translate(locale, "activity.trials.count", label=self.label(i, locale), count=n)
                for i, n in enumerate(state.tally)
            ]
            key = "activity.trials.after_rolls" if self.dice else "activity.trials.after_spins"
            text += ", " + plural(locale, key, state.done, tally=_join(counts, locale))
        return text

    def made_key(self) -> str:
        return "activity.trials.you_made"

    def limits(self) -> dict[str, Any]:
        # Sizes and the shape of the question; never the expected count and
        # never which choice is right (the module docstring says why).
        return {
            "weights": self.weights() if self.spinner else [],
            "dice": self.dice or 0,
            "outcomes": len(self.outcomes()),
            "choices": self.choices(),
            "max": MAX_TRIALS,
            "levels": LEVELS,
        }

    def say(self, locale: str) -> dict[str, Any]:
        return {
            "none": translate(locale, "activity.trials.none"),
            "made": translate(locale, "activity.trials.made"),
            "count": translate(locale, "activity.trials.count"),
            "after": translate(
                locale,
                "activity.trials.after_rolls" if self.dice else "activity.trials.after_spins",
            ),
            "after_one": translate(
                locale,
                "activity.trials.after_rolls_one"
                if self.dice
                else "activity.trials.after_spins_one",
            ),
            "and": translate(locale, "activity.and"),
            "labels": [self.label(i, locale) for i in range(len(self.outcomes()))],
            "choices": {c: self.choice_text(c, locale) for c in self.choices()},
        }

    def shown_choices(self, locale: str) -> list[tuple[str, str]]:
        """The choices as the page lists them. Outcomes keep their own order
        (a spinner's sectors, the dice totals), which is the question's order
        and says nothing about which is right; bands go up."""
        return [(c, self.choice_text(c, locale)) for c in self.choices()]

    # --- the no-script road ----------------------------------------------------

    def typed_right(self, text: str) -> bool:
        return text.strip() == self.right()

    def typed_example(self) -> str:
        return self.right()

    def typed_compare(self, text: str, locale: str) -> Comparison:
        picked = text.strip()
        made = (
            translate(locale, "activity.trials.made", choice=self.choice_text(picked, locale))
            if picked in self.choices()
            else (picked or "—")
        )
        asked = translate(
            locale, "activity.trials.made", choice=self.choice_text(self.right(), locale)
        )
        return Comparison(
            translate(locale, self.made_key(), made=made, asked=asked), made, asked, None, None
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: TrialsState, locale: str) -> Board:
        paths: list[Path] = []
        labels: list[Label] = []
        if self.spinner is not None:
            left_w = self._spinner(paths, labels, locale)
        else:
            left_w = self._dice(paths, labels, locale)

        # The bars: one column per outcome, its height the share of all trials
        # so far, in twentieths. Every height is drawn and one is shown.
        x0 = MARGIN + left_w + 2 * MARGIN
        top = MARGIN + 16
        base = top + BAR_H
        n = len(self.outcomes())
        width = n * (BAR_W + BAR_GAP) - BAR_GAP
        paths.append(Path(f"M{x0 - 4:.1f},{base:.1f} H{x0 + width + 4:.1f}", "sim-axis"))
        labels.append(
            Label(
                x0, MARGIN + 4, translate(locale, "activity.trials.chart"), size=11, anchor="start"
            )
        )
        pieces: list[Piece] = []
        for i in range(n):
            x = x0 + i * (BAR_W + BAR_GAP)
            level = bar_level(state.tally[i], state.done) if i < len(state.tally) else 0
            for step in range(1, LEVELS + 1):
                h = BAR_H * step / LEVELS
                pieces.append(
                    Piece(f"t{i}", step, "bar", x, base - h, BAR_W, h, shown=step == level)
                )
            labels.append(Label(x + BAR_W / 2, base + 12, self.label(i, locale), size=11))
        height = max(base + 24, 2 * RADIUS + 2 * MARGIN + 24) + MARGIN
        return Board(
            x0 + width + MARGIN,
            height,
            self.alt.get(locale),
            (Layer("base", tuple(paths), (), tuple(pieces), tuple(labels)),),
        )

    def _spinner(self, paths: list[Path], labels: list[Label], locale: str) -> float:
        cx = cy = MARGIN + RADIUS
        cy += 12
        total = sum(self.weights())
        angle = -math.pi / 2
        for i, (_, _, size) in enumerate(self.outcomes()):
            sweep = 2 * math.pi * size / total
            end = angle + sweep
            x1, y1 = cx + RADIUS * math.cos(angle), cy + RADIUS * math.sin(angle)
            x2, y2 = cx + RADIUS * math.cos(end), cy + RADIUS * math.sin(end)
            large = 1 if sweep > math.pi else 0
            paths.append(
                Path(
                    f"M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} "
                    f"A{RADIUS:.1f},{RADIUS:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z",
                    f"sim-sector sim-sector--{i % 3}",
                )
            )
            mid = angle + sweep / 2
            labels.append(
                Label(
                    cx + 0.6 * RADIUS * math.cos(mid),
                    cy + 0.6 * RADIUS * math.sin(mid),
                    self.label(i, locale),
                    size=12,
                )
            )
            angle = end
        # The pointer: a notch over the top of the wheel.
        paths.append(
            Path(
                f"M{cx - 7:.1f},{cy - RADIUS - 12:.1f} L{cx + 7:.1f},{cy - RADIUS - 12:.1f} "
                f"L{cx:.1f},{cy - RADIUS + 4:.1f} Z",
                "sim-pointer",
            )
        )
        return 2 * RADIUS

    def _dice(self, paths: list[Path], labels: list[Label], locale: str) -> float:
        faces = (5, 2)[: self.dice or 1]
        for d, face in enumerate(faces):
            x = MARGIN + d * (DIE + MARGIN)
            y = MARGIN + 30
            paths.append(Path(_square(x, y, DIE), "sim-die"))
            paths.append(Path(_pips(x, y, face), "sim-pip"))
        key = "activity.trials.dice_one" if self.dice == 1 else "activity.trials.dice"
        width = len(faces) * (DIE + MARGIN) - MARGIN
        labels.append(
            Label(MARGIN, MARGIN + 30 + DIE + 18, translate(locale, key), size=11, anchor="start")
        )
        return max(width, 2 * DIE)


def bar_level(count: int, total: int) -> int:
    """The bar step nearest to count/total, in twentieths; `trials.js` too."""
    if total <= 0:
        return 0
    return (2 * LEVELS * count + total) // (2 * total)


def xorshift32(x: int) -> int:
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= x >> 17
    x ^= (x << 5) & 0xFFFFFFFF
    return x & 0xFFFFFFFF


def simulate(seed: int, count: int, weights: list[int] | None, dice: int) -> tuple[int, ...]:
    """The tally after `count` trials from `seed`: the same function as
    `trialsSimulate` in `trials.js`, draw for draw.

    A spinner takes one number per spin, modulo the total of its sizes; each
    die takes one, modulo six. The bias of a modulo on a 32-bit number is far
    below anything a hundred trials can show.
    """
    x = seed & 0xFFFFFFFF or 1
    if weights:
        total = sum(weights)
        tally = [0] * len(weights)
        for _ in range(count):
            x = xorshift32(x)
            r = x % total
            for i, w in enumerate(weights):
                if r < w:
                    tally[i] += 1
                    break
                r -= w
        return tuple(tally)
    tally = [0] * (6 if dice == 1 else 11)
    for _ in range(count):
        x = xorshift32(x)
        roll = x % 6
        if dice == 2:
            x = xorshift32(x)
            roll += x % 6
        tally[roll] += 1
    return tuple(tally)


def _join(words: list[str], locale: str) -> str:
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {translate(locale, 'activity.and')} {words[-1]}"


def _square(x: float, y: float, s: float) -> str:
    return f"M{x:.1f},{y:.1f} h{s:.1f} v{s:.1f} h{-s:.1f} Z"


def _pips(x: float, y: float, face: int) -> str:
    """A die's face as small circles, the way dice are printed."""
    spots = {
        2: ((0.28, 0.28), (0.72, 0.72)),
        5: ((0.28, 0.28), (0.72, 0.28), (0.5, 0.5), (0.28, 0.72), (0.72, 0.72)),
    }[face]
    r = DIE * 0.08
    return " ".join(
        f"M{x + fx * DIE - r:.1f},{y + fy * DIE:.1f} a{r:.1f},{r:.1f} 0 1,0 {2 * r:.1f},0 "
        f"a{r:.1f},{r:.1f} 0 1,0 {-2 * r:.1f},0"
        for fx, fy in spots
    )


__all__ = ["TrialsActivity", "TrialsState", "bar_level", "simulate"]
