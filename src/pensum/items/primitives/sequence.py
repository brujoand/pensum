"""Cards put in order along a line, or around a cycle.

Life cycles, the water cycle, the church year, the events of a story, a
timeline: ordering is one act across subjects, so it is one primitive. The cards
are declared in the right order; the board opens them in a fixed jumble.

The pupil moves a card by dragging it onto another place in the line, by
tapping it and then the place, or with the move-up and move-down buttons on its
own row, which are the keyboard path. The line is always full, so every state
is an order and there is nothing to leave half done.

A cycle (`cycle: true`) has no first card: evaporation, condensation,
precipitation, runoff is the same wheel as condensation, precipitation, runoff,
evaporation. So a cycle is graded up to rotation, and the right answer drawn in
feedback is the declared order. Reversing a cycle is still wrong: the water
does not rain before it condenses.

Graded on the order.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.primitives.cards import (
    MAX_CARDS,
    Card,
    CardBoard,
    ChoiceActivity,
    Place,
    distinct,
    shuffled,
)
from pensum.items.text import AuthoredText


class SequenceState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Which card is at each place, first place first. Always every card once.
    order: tuple[int, ...]


class SequenceActivity(ChoiceActivity):
    """Put `cards`, declared in the right order, in order."""

    FALLBACK_KEY = "activity.sequence.ask"
    State = SequenceState

    kind: Literal["sequence"] = "sequence"
    cards: tuple[AuthoredText, ...] = Field(min_length=3, max_length=MAX_CARDS)
    cycle: bool = False

    @model_validator(mode="after")
    def _check(self) -> SequenceActivity:
        distinct(list(self.cards), "cards")
        return self

    def _right(self, order: tuple[int, ...]) -> bool:
        n = len(self.cards)
        if not self.cycle:
            return order == tuple(range(n))
        start = order.index(0)
        return all(order[(start + k) % n] == k for k in range(n))

    # --- rules -------------------------------------------------------------

    def initial(self) -> SequenceState:
        """A fixed jumble, never already right: a board that opens solved
        would be answered by pressing Check."""
        order = shuffled("|".join(c.nb for c in self.cards), len(self.cards))
        while self._right(tuple(order)):
            order = order[1:] + order[:1] if not self.cycle else order[::-1]
        return SequenceState(order=tuple(order))

    def solution(self) -> SequenceState:
        return SequenceState(order=tuple(range(len(self.cards))))

    def admits(self, state: SequenceState) -> bool:
        return sorted(state.order) == list(range(len(self.cards)))

    def grade_state(self, state: SequenceState) -> bool:
        return self._right(state.order)

    def near_misses(self) -> list[SequenceState]:
        """Two neighbours swapped, place by place."""
        n = len(self.cards)
        out = []
        for i in range(n - 1):
            order = list(range(n))
            order[i], order[i + 1] = order[i + 1], order[i]
            out.append(SequenceState(order=tuple(order)))
        order = list(range(n))
        order[0], order[-1] = order[-1], order[0]
        out.append(SequenceState(order=tuple(order)))
        return out

    def describe(self, state: SequenceState, locale: str) -> str:
        return " → ".join(self.cards[i].get(locale) for i in state.order)

    def limits(self) -> dict[str, int]:
        return {"cards": len(self.cards)}

    def say(self, locale: str) -> dict[str, object]:
        return {
            "cards": [c.get(locale) for c in self.cards],
            "up": translate(locale, "activity.sequence.up_card"),
            "down": translate(locale, "activity.sequence.down_card"),
        }

    # --- drawing -----------------------------------------------------------

    def board(self, state: SequenceState, locale: str) -> CardBoard:
        texts = [c.get(locale) for c in self.cards]
        places = tuple(
            Place(
                f"p{at}",
                translate(locale, "activity.sequence.place", n=at + 1),
                tuple(
                    Card(f"p{at}", i, text, state.order[at] == i) for i, text in enumerate(texts)
                ),
                "step",
                at + 1,
            )
            for at in range(len(texts))
        )
        return CardBoard(
            "partials/primitives/_sequence_board.html",
            self.alt.get(locale),
            places,
            kind="sequence",
            extra=(("cycle", self.cycle),),
        )
