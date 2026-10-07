"""The one item shape every Arkade game draws from.

A rule, the candidates, and which candidates satisfy the rule. A game decides
only how an item looks, so a generator never knows which game it is feeding.

Two kinds so far. A balloon is one statement, true or false, and the pupil's
two choices are the candidates: let it fly away (it is true) or pop it (it is
not). A memory pair is a sum and its answer, and both cards match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# What the pupil is asked, as the i18n key under `arkade.rule`. The rule is the
# instruction shown with the item, so it is part of the item.
Rule = Literal["statement", "spoken_word", "pair"]

# A balloon's two choices, as candidate indexes. Letting it fly away says the
# statement on it is true; bursting it says it is not.
FLY, POP = 0, 1
BALLOON_CHOICES = ("fly", "pop")


@dataclass(frozen=True)
class Item:
    """One question in an Arkade round."""

    # Stable across rounds, so evidence for the same fact lands on the same
    # item: "mat:7·8" whether the balloon said 56 or 48.
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
    # What a balloon shows: the statement, or one spelling of the spoken word.
    shown: str | None = None

    def __post_init__(self) -> None:
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError(f"{self.id}: candidates repeat")
        if not self.matches or not all(0 <= i < len(self.candidates) for i in self.matches):
            raise ValueError(f"{self.id}: matches must name at least one candidate")

    def is_match(self, index: int) -> bool:
        return index in self.matches


def balloon(
    id: str,  # noqa: A002 -- the field's name
    rule: Rule,
    shown: str,
    *,
    true: bool,
    answer: str,
    skill: str | None = None,
    spoken: str | None = None,
    language: str | None = None,
) -> Item:
    """One balloon: `shown` on it, and whether that is true."""
    return Item(
        id=id,
        rule=rule,
        candidates=BALLOON_CHOICES,
        matches=frozenset({FLY if true else POP}),
        answer=answer,
        skill=skill,
        spoken=spoken,
        language=language,
        shown=shown,
    )
