"""Explore a simulation: predict, move one slider and watch, then explain.

`explore_sim` in `docs/design/activities.md`: deliberately small. One slider,
one thing to watch, one question. PhET does broad open simulations far better,
and teachers already use them; what this primitive is for is the
predict-observe-explain loop, with the prediction recorded first so it cannot
be revised after seeing the result (the fair test builder's steps 3 to 5 in
`docs/design/subjects/naturfag.md`).

**The models are built in, and only their parameters are declared.** An item
names one of a small fixed set and fills in its numbers; there is no free-form
physics for an author to get subtly wrong and nobody to review:

  * `floats_sinks` -- objects of declared density dropped in water, one per
    slider stop. Lighter than water floats, as deep as its density says;
    heavier sinks to the bottom.
  * `states_of_matter` -- a box of particles of a declared substance at the
    declared temperatures: packed in a lattice below its melting point, close
    but loose below its boiling point, far apart above it. The melting and
    boiling points are a table here, not authored.
  * `moon_phase` -- the moon at eight places round the Earth with the sun to
    one side, and beside it the moon as seen from Norway at that place.

**Every slider stop is drawn by the server.** Each stop is one still, all of
them in the board, and the page only shows the one the slider is at, the way
the other boards show and hide their pieces. Nothing moves: a still per stop is
the calm version and the only version. A still shows what the model does -- a
cork at the surface, particles far apart, a half-lit moon -- and its label says
that literally; it never states the explanation the question asks for, which is
the pupil's to draw from what they saw.

**Graded on the explanation only.** The flow is prediction (a pick, locked by
the first move of the slider), observation, explanation (a pick). The
prediction is part of the submitted state, so it is recorded with the answer,
and it is never marked (principle: a prediction is not graded); the feedback
does not mention it. The explanation is right when it is the declared answer.

Without a script there is no slider to move: every still is shown in order
under the board, and the explanation is asked as radio buttons. The prediction
is left out there, because on a page that shows every result at once it could
not come first.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label, Path
from pensum.items.primitives import tiles
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer
from pensum.items.text import AuthoredText

Model = Literal["floats_sinks", "states_of_matter", "moon_phase"]

# Melting and boiling points at normal pressure, in whole degrees Celsius.
SUBSTANCES: dict[str, tuple[int, int]] = {
    "water": (0, 100),
    "ethanol": (-114, 78),
    "oxygen": (-218, -183),
    "iron": (1538, 2862),
}
WATER = 1.0
# How close to water's density still counts as neither floating nor sinking.
NEUTRAL = 0.02
MOON_PLACES = 8
PHASES = (
    "new",
    "waxing_crescent",
    "first_quarter",
    "waxing_gibbous",
    "full",
    "waning_gibbous",
    "last_quarter",
    "waning_crescent",
)


class SimChoice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,15}$")
    text: AuthoredText


class Predict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: AuthoredText
    choices: tuple[SimChoice, ...] = Field(min_length=2, max_length=4)


class Explain(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: AuthoredText
    choices: tuple[SimChoice, ...] = Field(min_length=3, max_length=4)
    answer: str

    @model_validator(mode="after")
    def _check(self) -> Explain:
        ids = [c.id for c in self.choices]
        if len(set(ids)) != len(ids):
            raise ValueError("two explanations share an id")
        if self.answer not in ids:
            raise ValueError(f"answer {self.answer!r} is not one of {ids}")
        return self


class SimObject(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: AuthoredText
    # Grams per cubic centimetre; water is 1.
    density: float = Field(gt=0, le=25)


class ExploreSimState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction: str | None = None
    # Set by the first move of the slider, and never unset: the lock.
    locked: bool = False
    stop: int = Field(default=0, ge=0)
    explain: str | None = None


class ExploreSimActivity(ActivityConfig):
    """Predict, watch one declared model across its slider stops, explain."""

    FALLBACK_KEY = "activity.explore_sim.ask"
    State = ExploreSimState

    kind: Literal["explore_sim"] = "explore_sim"
    model: Model
    objects: tuple[SimObject, ...] = Field(default=(), max_length=8)
    substance: Literal["water", "ethanol", "oxygen", "iron"] | None = None
    temperatures: tuple[int, ...] = Field(default=(), max_length=8)
    # The slider stop the board opens at.
    start: int = Field(default=0, ge=0)
    predict: Predict
    explain: Explain

    @model_validator(mode="after")
    def _check(self) -> ExploreSimActivity:
        if self.fallback is not None:
            raise ValueError("explore_sim asks the explanation without a script")
        if self.model == "floats_sinks":
            if len(self.objects) < 2 or self.substance or self.temperatures:
                raise ValueError("floats_sinks takes two to eight objects, and nothing else")
        elif self.model == "states_of_matter":
            if self.objects or self.substance is None or len(self.temperatures) < 2:
                raise ValueError("states_of_matter takes a substance and two to eight temperatures")
            if list(self.temperatures) != sorted(set(self.temperatures)):
                raise ValueError("temperatures go up, each once")
            if set(self.temperatures) & set(SUBSTANCES[self.substance]):
                raise ValueError("a temperature exactly at melting or boiling is neither state")
        elif self.objects or self.substance or self.temperatures:
            raise ValueError("moon_phase takes no parameters: its eight places are fixed")
        if self.start >= self.stops():
            raise ValueError(f"start {self.start} is past the last stop")
        ids = [c.id for c in self.predict.choices]
        if len(set(ids)) != len(ids):
            raise ValueError("two predictions share an id")
        return self

    # --- the model -------------------------------------------------------------

    def stops(self) -> int:
        if self.model == "floats_sinks":
            return len(self.objects)
        if self.model == "states_of_matter":
            return len(self.temperatures)
        return MOON_PLACES

    def phase(self, stop: int) -> str:
        """The state of matter, how an object sits, or the moon's phase."""
        if self.model == "floats_sinks":
            density = self.objects[stop].density
            if abs(density - WATER) <= NEUTRAL:
                return "neutral"
            return "floats" if density < WATER else "sinks"
        if self.model == "states_of_matter":
            melt, boil = SUBSTANCES[self.substance or "water"]
            t = self.temperatures[stop]
            return "solid" if t < melt else "liquid" if t < boil else "gas"
        return PHASES[stop]

    def stop_label(self, stop: int, locale: str) -> str:
        if self.model == "floats_sinks":
            return self.objects[stop].label.get(locale)
        if self.model == "states_of_matter":
            return translate(locale, "activity.explore_sim.degrees", t=self.temperatures[stop])
        return translate(locale, "activity.explore_sim.place", n=stop + 1, of=MOON_PLACES)

    def observation(self, stop: int, locale: str) -> str:
        """What the still at a stop shows, in words. Never the explanation."""
        key = f"activity.explore_sim.{self.model}.{self.phase(stop)}"
        return translate(locale, key, thing=self.stop_label(stop, locale))

    def slider_label(self, locale: str) -> str:
        return translate(locale, f"activity.explore_sim.{self.model}.slider")

    def explanation(self, choice: str, locale: str) -> str:
        return next((c.text.get(locale) for c in self.explain.choices if c.id == choice), choice)

    def shown(self, choices: tuple[SimChoice, ...]) -> list[SimChoice]:
        """Choices in a stable order that is not the authored one."""
        return sorted(choices, key=lambda c: tiles.mix(self.model, c.id, c.text.nb))

    # --- rules -----------------------------------------------------------------

    def initial(self) -> ExploreSimState:
        return ExploreSimState(stop=self.start)

    def solution(self) -> ExploreSimState:
        # Any prediction will do: it is never graded. The first is recorded so
        # the solved state is one the page could send.
        return ExploreSimState(
            prediction=self.predict.choices[0].id,
            locked=True,
            stop=self.start,
            explain=self.explain.answer,
        )

    def admits(self, state: ExploreSimState) -> bool:
        if not 0 <= state.stop < self.stops():
            return False
        if state.prediction is not None and state.prediction not in {
            c.id for c in self.predict.choices
        }:
            return False
        if state.explain is not None and state.explain not in {c.id for c in self.explain.choices}:
            return False
        # The order of the loop: the slider moves only after a prediction, and
        # the explanation comes after the slider has moved.
        if state.stop != self.start and not state.locked:
            return False
        if state.locked and state.prediction is None:
            return False
        return state.explain is None or state.locked

    def grade_state(self, state: ExploreSimState) -> bool:
        return state.explain == self.explain.answer

    def default_fallback(self) -> float:
        return 0.0

    def fallback_prompt(self, locale: str) -> str:
        return self.explain.prompt.get(locale)

    def describe(self, state: ExploreSimState, locale: str) -> str:
        if state.explain is not None:
            return translate(
                locale, "activity.explore_sim.made", choice=self.explanation(state.explain, locale)
            )
        if state.locked:
            return translate(locale, "activity.explore_sim.observed")
        if state.prediction is not None:
            return translate(locale, "activity.explore_sim.predicted")
        return translate(locale, "activity.explore_sim.none")

    def made_key(self) -> str:
        return "activity.explore_sim.you_made"

    def limits(self) -> dict[str, Any]:
        # Which ids exist, never which explanation is right.
        return {
            "stops": self.stops(),
            "start": self.start,
            "predict": [c.id for c in self.predict.choices],
            "explain": [c.id for c in self.explain.choices],
        }

    def say(self, locale: str) -> dict[str, Any]:
        return {
            "none": translate(locale, "activity.explore_sim.none"),
            "predicted": translate(locale, "activity.explore_sim.predicted"),
            "observed": translate(locale, "activity.explore_sim.observed"),
            "made": translate(locale, "activity.explore_sim.made"),
            "explain": {c.id: c.text.get(locale) for c in self.explain.choices},
            "stops": [
                f"{self.stop_label(i, locale)}: {self.observation(i, locale)}"
                for i in range(self.stops())
            ],
        }

    # --- the no-script road ----------------------------------------------------

    def typed_right(self, text: str) -> bool:
        return text.strip() == self.explain.answer

    def typed_example(self) -> str:
        return self.explain.answer

    def typed_compare(self, text: str, locale: str) -> Comparison:
        picked = text.strip()
        ids = {c.id for c in self.explain.choices}
        made = (
            translate(locale, "activity.explore_sim.made", choice=self.explanation(picked, locale))
            if picked in ids
            else (picked or "—")
        )
        asked = self.describe(self.solution(), locale)
        return Comparison(
            translate(locale, self.made_key(), made=made, asked=asked), made, asked, None, None
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: ExploreSimState, locale: str) -> Board:
        """Every still, the one at the state's stop shown and the rest off."""
        width, height = self._size()
        stop = state.stop if 0 <= state.stop < self.stops() else self.start
        layers = tuple(self._still(i, locale, off=i != stop) for i in range(self.stops()))
        return Board(width, height, self.alt.get(locale), layers)

    def still_board(self, stop: int, locale: str) -> Board:
        """One stop's still on its own, for the no-script listing."""
        width, height = self._size()
        return Board(width, height, self.observation(stop, locale), (self._still(stop, locale),))

    def _size(self) -> tuple[float, float]:
        return {
            "floats_sinks": (260.0, 214.0),
            "states_of_matter": (340.0, 196.0),
            "moon_phase": (340.0, 216.0),
        }[self.model]

    def _still(self, stop: int, locale: str, off: bool = False) -> Layer:
        draw = {
            "floats_sinks": self._tank,
            "states_of_matter": self._particles,
            "moon_phase": self._moon,
        }[self.model]
        paths, labels = draw(stop, locale)
        role = f"still still-{stop}" + (" is-off" if off else "")
        return Layer(role, tuple(paths), labels=tuple(labels))

    def _tank(self, stop: int, locale: str) -> tuple[list[Path], list[Label]]:
        width, height = self._size()
        left, right, top, bottom, surface = 50.0, 210.0, 48.0, 178.0, 92.0
        paths = [
            Path(f"M{left},{surface} H{right} V{bottom} H{left} Z", "sim-water"),
            Path(f"M{left},{top} V{bottom} H{right} V{top}", "sim-tank"),
        ]
        density = self.objects[stop].density
        block_w, block_h = 48.0, 30.0
        if self.phase(stop) == "sinks":
            y = bottom - block_h
        elif self.phase(stop) == "neutral":
            y = surface + 4
        else:
            # Floating, as deep as its density: a block half as dense as water
            # sits half under.
            y = surface - block_h * (1 - density / WATER)
        x = (left + right - block_w) / 2
        paths.append(Path(f"M{x},{y:.1f} h{block_w} v{block_h} h{-block_w} Z", "sim-object"))
        labels = [
            Label(width / 2, 22, self.stop_label(stop, locale), size=13),
            Label(width / 2, height - 14, self.observation(stop, locale), size=11),
        ]
        return paths, labels

    def _particles(self, stop: int, locale: str) -> tuple[list[Path], list[Label]]:
        width, height = self._size()
        left, top, right, bottom = 24.0, 18.0, 244.0, 150.0
        paths = [Path(f"M{left},{top} H{right} V{bottom} H{left} Z", "sim-tank")]
        state = self.phase(stop)
        r = 6.0
        if state == "solid":
            centres = [
                (110 + 13 * c, bottom - r - 1 - 13 * row) for row in range(4) for c in range(4)
            ]
            motion = [
                f"M{x - 9:.1f},{y - 3:.1f} v6 M{x + 9:.1f},{y - 3:.1f} v6" for x, y in centres[::5]
            ]
        elif state == "liquid":
            centres = [
                (
                    left + 20 + 15 * (i % 8) + (i // 8) * 7 + _JITTER[i][0] * 2,
                    bottom - r - 1 - 13 * (i // 8) - abs(_JITTER[i][1]) * 2,
                )
                for i in range(16)
            ]
            motion = [f"M{x - 4:.1f},{y - 10:.1f} q6,-4 12,0" for x, y in centres[::4]]
        else:
            centres = [
                (
                    left + 22 + 58 * (i % 4) + _JITTER[i][0] * 6,
                    top + 16 + 32 * (i // 4) + _JITTER[i][1] * 5,
                )
                for i in range(16)
            ]
            motion = [
                f"M{x + 8:.1f},{y:.1f} l16,{_JITTER[i][1] * 3:.1f}"
                for i, (x, y) in enumerate(centres[::3])
            ]
        paths.append(
            Path(
                " ".join(
                    f"M{x - r:.1f},{y:.1f} a{r},{r} 0 1,0 {2 * r},0 a{r},{r} 0 1,0 {-2 * r},0"
                    for x, y in centres
                ),
                "sim-particle",
            )
        )
        paths.append(Path(" ".join(motion), "sim-motion"))
        # The thermometer: how full is where this stop sits among all of them.
        tx, t_top, t_bottom = 290.0, top, bottom
        low, high = self.temperatures[0], self.temperatures[-1]
        share = 0.15 + 0.7 * (self.temperatures[stop] - low) / (high - low)
        level = t_bottom - share * (t_bottom - t_top)
        paths.append(Path(f"M{tx - 6},{t_top} h12 V{t_bottom} h-12 Z", "sim-thermo"))
        paths.append(Path(f"M{tx - 3},{level:.1f} h6 V{t_bottom - 2} h-6 Z", "sim-thermo-fill"))
        labels = [
            Label(tx, t_bottom + 16, self.stop_label(stop, locale), size=12),
            Label(left, height - 12, self.observation(stop, locale), size=11, anchor="start"),
        ]
        return paths, labels

    def _moon(self, stop: int, locale: str) -> tuple[list[Path], list[Label]]:
        width, height = self._size()
        ex, ey, orbit, moon = 100.0, 100.0, 62.0, 11.0
        paths = [
            Path(_circle(ex, ey, orbit), "sim-orbit"),
            Path(_circle(ex, ey, 14), "sim-earth"),
        ]
        # Light from the sun, off to the right.
        paths.append(
            Path(
                " ".join(
                    f"M{206},{y} H{180} M{186},{y - 4} L{180},{y} L{186},{y + 4}"
                    for y in (70, 100, 130)
                ),
                "sim-light",
            )
        )
        angle = 2 * math.pi * stop / MOON_PLACES
        mx, my = ex + orbit * math.cos(angle), ey - orbit * math.sin(angle)
        # In the view from above, the half facing the sun is lit.
        paths.append(Path(_half(mx, my, moon, right=False), "sim-dark"))
        paths.append(Path(_half(mx, my, moon, right=True), "sim-lit"))
        # As seen from Norway.
        sx, sy, big = 282.0, 100.0, 34.0
        paths.append(Path(_circle(sx, sy, big), "sim-dark"))
        lit = _lit(sx, sy, big, stop)
        if lit:
            paths.append(Path(lit, "sim-lit"))
        paths.append(Path(_circle(sx, sy, big), "sim-moon-outline"))
        labels = [
            Label(
                206,
                52,
                translate(locale, "activity.explore_sim.moon_phase.sun"),
                size=11,
                anchor="end",
            ),
            Label(ex, ey, translate(locale, "activity.explore_sim.moon_phase.earth"), size=8),
            Label(
                sx,
                sy - big - 12,
                translate(locale, "activity.explore_sim.moon_phase.seen"),
                size=11,
            ),
            Label(12, height - 30, self.stop_label(stop, locale), size=11, anchor="start"),
            Label(12, height - 12, self.observation(stop, locale), size=11, anchor="start"),
        ]
        return paths, labels


# A fixed scatter, so a liquid and a gas look loose without being random: the
# same item draws the same stills every time.
_JITTER = (
    (1, -2), (-2, 1), (2, 2), (0, -1), (-1, 2), (2, -2), (-2, -1), (1, 1),
    (0, 2), (-1, -2), (2, 0), (-2, 2), (1, -1), (0, 1), (-1, 0), (2, 1),
)  # fmt: skip


def _circle(cx: float, cy: float, r: float) -> str:
    return (
        f"M{cx - r:.1f},{cy:.1f} a{r:.1f},{r:.1f} 0 1,0 {2 * r:.1f},0 "
        f"a{r:.1f},{r:.1f} 0 1,0 {-2 * r:.1f},0"
    )


def _half(cx: float, cy: float, r: float, *, right: bool) -> str:
    """The right or left half of a circle."""
    sweep = 1 if right else 0
    return f"M{cx:.1f},{cy - r:.1f} A{r:.1f},{r:.1f} 0 0 {sweep} {cx:.1f},{cy + r:.1f} Z"


def _lit(cx: float, cy: float, r: float, place: int) -> str:
    """The lit part of the moon as seen from the northern hemisphere.

    Place 0 is new (between the Earth and the sun) and place 4 full. Waxing,
    the right side is lit; waning, the left. The terminator is half an ellipse
    whose width is |cos| of the angle, bulging towards the lit edge while the
    lit part is a crescent and away from it once it is gibbous.
    """
    if place == 0:
        return ""
    if place == 4:
        return _circle(cx, cy, r)
    angle = 2 * math.pi * place / MOON_PLACES
    rx = abs(r * math.cos(angle))
    waxing = place < 4
    crescent = math.cos(angle) > 0
    top, bottom = f"{cx:.1f},{cy - r:.1f}", f"{cx:.1f},{cy + r:.1f}"
    if waxing:
        edge = f"A{r:.1f},{r:.1f} 0 0 1 {bottom}"
        sweep = 0 if crescent else 1
    else:
        edge = f"A{r:.1f},{r:.1f} 0 0 0 {bottom}"
        sweep = 1 if crescent else 0
    return f"M{top} {edge} A{rx:.1f},{r:.1f} 0 0 {sweep} {top} Z"


__all__ = ["SUBSTANCES", "ExploreSimActivity", "ExploreSimState"]
