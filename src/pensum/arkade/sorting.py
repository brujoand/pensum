"""Sorting cards: a number or a letter is spoken and shown, and belongs in one pile.

Nothing here is authored. A sorting is a set of piles and the cards that belong
in each, so a round can ask for each pile about as often as the others
and never deal the same card twice. Sorting spoken words by a sound (`ch`
beside `sh`) needs a reviewed word list, and is not here yet.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from random import Random

from pensum.arkade.items import Item, card

ODD_EVEN = ("even", "odd")
LETTERS = ("vowel", "consonant")

# The Norwegian alphabet, which is what a pupil in norsk is taught. Y is a
# vowel in Norwegian.
VOWELS = "aeiouyæøå"
CONSONANTS = "bcdfghjklmnpqrstvwxz"


@dataclass(frozen=True)
class Sorting:
    """One sorting game: its piles, the skill it is evidence for, and the
    cards that go in each pile."""

    name: str
    piles: tuple[str, ...]
    skill: str | None
    # Every card that belongs in `pile`, in a round for `grade`.
    cards: Callable[[str, int], Sequence[str]]
    # The last year the game is offered to: the year its goal is to be met by.
    last_year: int
    # The language a card is spoken in, or None for the language of the page:
    # a number is said in the pupil's language, a Norwegian letter in Norwegian.
    language: str | None = None

    def items(self, grade: int, language: str, rng: Random, count: int) -> list[Item]:
        """A round of `count` cards, no two alike, each pile about as often as the others."""
        spoken_in = self.language or language
        seen: set[str] = set()
        items: list[Item] = []
        for _ in range(count):
            pile = rng.choice(self.piles)
            left = [shown for shown in self.cards(pile, grade) if shown not in seen]
            if not left:
                raise ValueError(f"{self.name}: too few cards for the pile {pile}")
            shown = rng.choice(left)
            seen.add(shown)
            items.append(
                card(
                    f"sort:{self.name}:{shown.lower()}",
                    shown,
                    self.piles,
                    pile,
                    skill=self.skill,
                    # Lower case: a voice reads a capital alone as "capital A".
                    spoken=shown.lower(),
                    language=spoken_in,
                )
            )
        return items


# Odd and even is a goal of year 2 (KM13231), and so is knowing the letters.
# A pupil past it has no use for either sorting, so neither is offered.
LAST_YEAR = 2


def top_for(grade: int) -> int:
    """The largest number a pupil in `grade` sorts: the numbers they count with.

    To 20 in year 1, and to 100 in year 2, when counting to 100 is the goal.
    """
    return 20 if grade <= 1 else 100


def _numbers(pile: str, grade: int) -> Sequence[str]:
    return [str(n) for n in range(2 if pile == "even" else 1, top_for(grade) + 1, 2)]


def _letters(pile: str, grade: int) -> Sequence[str]:  # noqa: ARG001 -- one alphabet for every year
    return (VOWELS if pile == "vowel" else CONSONANTS).upper()


NUMBERS = Sorting("odd-even", ODD_EVEN, "mat.counting.odd-even", _numbers, LAST_YEAR)
# No skill: the letter skills are about the sound a letter has, and naming a
# letter a vowel shows something else.
ALPHABET = Sorting("letters", LETTERS, None, _letters, LAST_YEAR, language="nb")
