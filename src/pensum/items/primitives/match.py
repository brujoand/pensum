"""Two columns, and a link from each thing on the left to one on the right.

Term to definition, festival to tradition, a Swedish word to its Norwegian
one, a situation to the right that protects it. The pairs are declared side by
side, which is how a reviewer checks them; the right-hand column is shown in a
fixed jumble so that its order does not give the answer.

The pupil links a pair by tapping one side and then the other, in either
order, or by dragging a right-hand card onto a row. Each row also has its own
menu under the board, which is the keyboard path. A right-hand card can be in
one row at a time: linking it elsewhere moves it. The linked card is written
into the row beside its partner, so a finished board reads as a list of pairs
rather than as lines that have to be followed with the eye.

Graded on the set of pairs: every row linked to its own partner.
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

NONE = -1


class Pair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left: AuthoredText
    right: AuthoredText


class MatchState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Per left-hand row: the right-hand card linked to it, or -1.
    pairs: tuple[int, ...]


class MatchActivity(ChoiceActivity):
    """Link each `left` to its `right`."""

    FALLBACK_KEY = "activity.match.ask"
    State = MatchState

    kind: Literal["match"] = "match"
    pairs: tuple[Pair, ...] = Field(min_length=3, max_length=MAX_CARDS)

    @model_validator(mode="after")
    def _check(self) -> MatchActivity:
        distinct([p.left for p in self.pairs], "left-hand cards")
        distinct([p.right for p in self.pairs], "right-hand cards")
        return self

    def right_order(self) -> list[int]:
        """The right-hand column as shown: a fixed jumble of the authored order."""
        return shuffled("|".join(p.right.nb for p in self.pairs), len(self.pairs))

    def made_key(self) -> str:
        return "activity.cards.you_linked"

    # --- rules -------------------------------------------------------------

    def initial(self) -> MatchState:
        return MatchState(pairs=(NONE,) * len(self.pairs))

    def solution(self) -> MatchState:
        return MatchState(pairs=tuple(range(len(self.pairs))))

    def admits(self, state: MatchState) -> bool:
        n = len(self.pairs)
        if len(state.pairs) != n or not all(NONE <= p < n for p in state.pairs):
            return False
        linked = [p for p in state.pairs if p != NONE]
        return len(linked) == len(set(linked))

    def grade_state(self, state: MatchState) -> bool:
        return state.pairs == tuple(range(len(self.pairs)))

    def near_misses(self) -> list[MatchState]:
        """Two neighbouring rows with their partners crossed."""
        n = len(self.pairs)
        out = []
        for i in range(n - 1):
            pairs = list(range(n))
            pairs[i], pairs[i + 1] = pairs[i + 1], pairs[i]
            out.append(MatchState(pairs=tuple(pairs)))
        return out

    def describe(self, state: MatchState, locale: str) -> str:
        none = translate(locale, "activity.cards.none")
        return "; ".join(
            f"{pair.left.get(locale)} – "
            f"{self.pairs[linked].right.get(locale) if linked != NONE else none}"
            for pair, linked in zip(self.pairs, state.pairs, strict=True)
        )

    def limits(self) -> dict[str, int]:
        return {"cards": len(self.pairs)}

    def say(self, locale: str) -> dict[str, object]:
        return {
            "none": translate(locale, "activity.cards.none"),
            "left": [p.left.get(locale) for p in self.pairs],
            "right": [p.right.get(locale) for p in self.pairs],
            "used": translate(locale, "activity.match.used"),
        }

    # --- drawing -----------------------------------------------------------

    def board(self, state: MatchState, locale: str) -> CardBoard:
        rights = [p.right.get(locale) for p in self.pairs]
        places = tuple(
            Place(
                f"l{row}",
                pair.left.get(locale),
                tuple(
                    Card(f"l{row}", j, text, state.pairs[row] == j) for j, text in enumerate(rights)
                ),
                "row",
                row + 1,
            )
            for row, pair in enumerate(self.pairs)
        )
        supply = tuple(Card("supply", j, rights[j]) for j in self.right_order())
        return CardBoard(
            "partials/primitives/_match_board.html",
            self.alt.get(locale),
            places,
            supply,
            kind="match",
            # Its own words, so it draws without the page's `t` (see sequence).
            extra=(("none", translate(locale, "activity.cards.none")),),
        )
