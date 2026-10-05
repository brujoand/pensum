"""The one item shape every Arkade game draws from.

A rule, the candidates, and which candidates satisfy the rule. A balloon game
pops the matching balloon; memory pairs and invaders read the same fields. A
game decides only how an item looks, so a generator never knows which game it
is feeding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# What the pupil looks for, as the i18n key under `arkade.rule`. The rule is the
# instruction shown above the candidates, so it is part of the item: two items
# with the same candidates and a different rule are different questions.
Rule = Literal["false_statement", "spoken_word"]


@dataclass(frozen=True)
class Item:
    """One question in an Arkade round."""

    # Stable across rounds, so evidence for the same fact lands on the same
    # item: "mat:7x8" whatever the false statement beside it was.
    id: str
    rule: Rule
    candidates: tuple[str, ...]
    matches: frozenset[int]
    # The correct form, shown after every answer whatever was picked: rule 7 of
    # the design, because a spelling game puts misspellings on screen.
    answer: str
    # The skill an answer is evidence for, or None where no skill fits closely
    # enough to move mastery. None records nothing; it never guesses.
    skill: str | None = None
    # A word the page speaks aloud before the pupil chooses, and in which
    # language. Only spelling items have one.
    spoken: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError(f"{self.id}: candidates repeat")
        if not self.matches or not all(0 <= i < len(self.candidates) for i in self.matches):
            raise ValueError(f"{self.id}: matches must name at least one candidate")

    def is_match(self, index: int) -> bool:
        return index in self.matches
