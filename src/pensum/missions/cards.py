"""The printable cards, as shapes; their words are in the locale files.

A card is a script: a few numbered steps in a fixed order, and for some cards a
set of sentence starters. A conversation with a written structure is
predictable, and that is what makes it possible for a pupil who finds the
unwritten rules of open conversation hard (docs/design/subjects/norsk.md).

The text is UI text, not mission data, because it is the same card for every
mission that uses it: `missions.card.<kind>.title`, `.step1` … `.stepN` and
`.starter1` … `.starterN`. What lives here is how many of each there are, and
whether the printed card leaves a line to write on under each step. A test
holds the two in step, so a card cannot print a key name instead of a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    kind: str
    steps: int
    starters: int = 0
    # A line under each step, for the cards that are filled in rather than
    # read: a risk card is written before the experiment, not recited.
    write_in: bool = False

    def key(self, part: str) -> str:
        return f"missions.card.{self.kind}.{part}"

    @property
    def step_keys(self) -> tuple[str, ...]:
        return tuple(self.key(f"step{n}") for n in range(1, self.steps + 1))

    @property
    def starter_keys(self) -> tuple[str, ...]:
        return tuple(self.key(f"starter{n}") for n in range(1, self.starters + 1))

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.key("title"), self.key("intro"), *self.step_keys, *self.starter_keys)


CARDS: dict[str, Card] = {
    card.kind: card
    for card in (
        Card("turn", steps=3, starters=3),
        Card("feedback", steps=4, starters=2),
        Card("question", steps=3),
        Card("ladder", steps=3),
        Card("interview", steps=4, starters=5),
        Card("risk", steps=5, write_in=True),
        Card("solve_it", steps=5, starters=2),
        Card("method", steps=6),
        Card("checklist", steps=4),
    )
}
