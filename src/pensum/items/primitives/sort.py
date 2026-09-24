"""Cards sorted into two to four labelled bins, or into a two-set Venn diagram.

Classifying is the same act in every subject: floats or sinks, fact or opinion,
which tradition a festival belongs to, which class a word is. So it is one
primitive, with the bins and the cards as content.

The pupil moves a card by dragging it, by tapping it and then a bin, or with
the card's own menu under the board, which is the keyboard path. Every card
starts outside the bins, so an unsorted card is visibly unsorted rather than
quietly counted as a guess.

A Venn diagram is the same board with three places: only the first set, both,
and only the second. It is declared as two `bins` and `venn: true`, and a card
that belongs to both says `bin: both`. The overlap is the point of it -- prayer
is in Christianity and in Islam -- so it is a place of its own, not two cards.

Graded on bin contents: every card in the bin it declares, and none left out.
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
    join_words,
)
from pensum.items.text import AuthoredText

TRAY = -1


class SortCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: AuthoredText
    # The bin it belongs in, counted from 0, or "both" on a Venn diagram.
    bin: int | Literal["both"]


class SortState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Per card, in authored order: the place it is in, or -1 for not yet sorted.
    place: tuple[int, ...]


class SortActivity(ChoiceActivity):
    """Sort `cards` into `bins`."""

    FALLBACK_KEY = "activity.sort.ask"
    State = SortState

    kind: Literal["sort"] = "sort"
    bins: tuple[AuthoredText, ...] = Field(min_length=2, max_length=4)
    cards: tuple[SortCard, ...] = Field(min_length=3, max_length=MAX_CARDS)
    venn: bool = False

    @model_validator(mode="after")
    def _check(self) -> SortActivity:
        distinct([c.text for c in self.cards], "cards")
        distinct(list(self.bins), "bins")
        if self.venn and len(self.bins) != 2:
            raise ValueError("a Venn diagram has exactly two sets")
        for card in self.cards:
            if card.bin == "both":
                if not self.venn:
                    raise ValueError("bin: both needs venn: true")
            elif not 0 <= card.bin < len(self.bins):
                raise ValueError(f"no bin {card.bin} for {card.text.nb!r}")
        if len(set(self.answer())) < 2:
            raise ValueError("every card in one bin is not a sorting")
        return self

    # --- places ------------------------------------------------------------

    @property
    def regions(self) -> int:
        """How many places a card can be sorted into."""
        return 3 if self.venn else len(self.bins)

    def region_of(self, card: SortCard) -> int:
        if not self.venn:
            return int(card.bin)
        return {0: 0, "both": 1, 1: 2}[card.bin]

    def answer(self) -> tuple[int, ...]:
        return tuple(self.region_of(c) for c in self.cards)

    def titles(self, locale: str) -> list[str]:
        names = [b.get(locale) for b in self.bins]
        if not self.venn:
            return names
        return [
            translate(locale, "activity.sort.only", name=names[0]),
            translate(locale, "activity.sort.both"),
            translate(locale, "activity.sort.only", name=names[1]),
        ]

    # --- rules -------------------------------------------------------------

    def initial(self) -> SortState:
        return SortState(place=(TRAY,) * len(self.cards))

    def solution(self) -> SortState:
        return SortState(place=self.answer())

    def admits(self, state: SortState) -> bool:
        return len(state.place) == len(self.cards) and all(
            TRAY <= p < self.regions for p in state.place
        )

    def grade_state(self, state: SortState) -> bool:
        return state.place == self.answer()

    def near_misses(self) -> list[SortState]:
        """One card in the neighbouring bin, card by card."""
        right = self.answer()
        out = []
        for i, region in enumerate(right):
            place = list(right)
            place[i] = (region + 1) % self.regions
            out.append(SortState(place=tuple(place)))
        return out

    def describe(self, state: SortState, locale: str) -> str:
        none = translate(locale, "activity.cards.none")
        parts = []
        for region, title in enumerate(self.titles(locale)):
            inside = [
                c.text.get(locale)
                for c, p in zip(self.cards, state.place, strict=True)
                if p == region
            ]
            parts.append(f"{title}: {join_words(inside, locale) or none}")
        left = [
            c.text.get(locale) for c, p in zip(self.cards, state.place, strict=True) if p == TRAY
        ]
        if left:
            parts.append(f"{translate(locale, 'activity.cards.tray')}: {join_words(left, locale)}")
        return "; ".join(parts)

    def limits(self) -> dict[str, int]:
        return {"cards": len(self.cards), "regions": self.regions}

    def say(self, locale: str) -> dict[str, object]:
        return {
            "and": translate(locale, "activity.and"),
            "none": translate(locale, "activity.cards.none"),
            "tray": translate(locale, "activity.cards.tray"),
            "titles": self.titles(locale),
            "cards": [c.text.get(locale) for c in self.cards],
        }

    # --- drawing -----------------------------------------------------------

    def board(self, state: SortState, locale: str) -> CardBoard:
        texts = [c.text.get(locale) for c in self.cards]

        def place(name: str, title: str, region: int, role: str) -> Place:
            cards = tuple(
                Card(name, i, text, state.place[i] == region) for i, text in enumerate(texts)
            )
            return Place(name, title, cards, role)

        places = [place("tray", translate(locale, "activity.cards.tray"), TRAY, "tray")]
        for region, title in enumerate(self.titles(locale)):
            role = "bin"
            if self.venn:
                role = ("bin venn-a", "bin venn-both", "bin venn-b")[region]
            places.append(place(f"r{region}", title, region, role))
        return CardBoard(
            "partials/primitives/_sort_board.html",
            self.alt.get(locale),
            tuple(places),
            kind="sort",
            extra=(("venn", self.venn), ("sets", tuple(b.get(locale) for b in self.bins))),
        )
