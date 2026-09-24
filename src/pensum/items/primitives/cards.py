"""What the card primitives share: sort, sequence, match, label and highlight.

The number primitives build a quantity, and without a script the same quantity
is asked as a typed number. These five build an *arrangement* -- cards in bins,
cards in an order, pairs, labels on a picture, marked words -- and there is no
number to type. So their no-script road is a choice: the right arrangement and
a few near misses, each one a radio button whose value is the whole state,
serialised exactly as the page's script would write it. The typed road and the
built road therefore meet in one place again: the state is graded by the same
`grade_state`, whichever way it arrived.

The near misses are made, not authored: each primitive knows the smallest
mistakes on its own board (one card in the wrong bin, two neighbours swapped,
two pairs crossed, one word too many), and a mistake of that size is the one a
pupil actually makes. They are shown in an order fixed by the states
themselves, so the right one is not always first and a reload does not move
it.

The text-heavy four draw their board as HTML rather than SVG. A card is a
sentence as often as a word, SVG text does not wrap, and a screen reader reads
HTML text where it can only be told what an SVG shows. The model is the one the
SVG boards use: every card the board could show is drawn in every place it
could be, and the script only shows and hides them. `label` answers on a
picture, so it stays SVG.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from pensum.i18n import translate
from pensum.items.primitives.base import ActivityConfig, Comparison, grade
from pensum.items.text import AuthoredText

# How many options the no-script question offers, the right one included, and
# the fewest that still make it a question rather than a confirmation.
MOST_CHOICES = 4
FEWEST_CHOICES = 3
MAX_CARDS = 8


@dataclass(frozen=True)
class Card:
    """One card in one place. Drawn whether or not it is there now."""

    zone: str
    index: int
    text: str
    shown: bool = True


@dataclass(frozen=True)
class Place:
    """Somewhere cards go: a bin, a position in a line, a row of a match."""

    name: str
    title: str
    cards: tuple[Card, ...] = ()
    role: str = ""
    # A number shown beside the place, when places are numbered.
    number: int = 0


@dataclass(frozen=True)
class CardBoard:
    """An HTML board. `template` is the partial that draws it, and is what
    tells the shared partials this is not an SVG `Board`."""

    template: str
    alt: str
    places: tuple[Place, ...]
    # The cards that are always there, as a column to take from (a match's
    # right-hand side) or as the text itself (a highlight's words).
    supply: tuple[Card, ...] = ()
    kind: str = ""
    # Anything else a board partial needs, per primitive.
    extra: tuple[tuple[str, Any], ...] = ()

    def get(self, key: str, default: Any = None) -> Any:
        return dict(self.extra).get(key, default)


def order_key(seed: str, index: int | str) -> str:
    """A fixed, arbitrary position for `index`: the same on every load."""
    return hashlib.sha256(f"{seed}:{index}".encode()).hexdigest()


def shuffled(seed: str, count: int) -> list[int]:
    """0..count-1 in an order fixed by `seed`, never left as it was.

    Used where the authored order would give the answer away: a match's right
    column, a label's tray. Not random, so a page and its feedback agree, and a
    reviewer sees what a pupil sees.
    """
    order = sorted(range(count), key=lambda i: order_key(seed, i))
    if count > 1 and order == list(range(count)):
        order = order[1:] + order[:1]
    return order


def join_words(words: list[str], locale: str) -> str:
    """ "a, b og c"."""
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {translate(locale, 'activity.and')} {words[-1]}"


def distinct(texts: list[AuthoredText], what: str) -> None:
    """Two cards that read the same cannot be told apart, in either language."""
    for locale in ("nb", "en"):
        seen = [t.get(locale) for t in texts]
        if len(set(seen)) != len(seen):
            raise ValueError(f"two {what} read the same in {locale}")


class ChoiceActivity(ActivityConfig):
    """An `ActivityConfig` whose no-script road is a choice between states."""

    # No typed fallback: there is no number to type. The choice is made from the
    # board's own near misses, so there is nothing to declare either.
    fallback: None = None

    def near_misses(self) -> list[BaseModel]:
        """Wrong states one small mistake away from the solution, best first."""
        raise NotImplementedError

    def default_fallback(self) -> float:
        return math.nan

    def fallback_choices(self, locale: str) -> list[tuple[str, str]]:
        """(value, words) for each option: the solution and its near misses."""
        right = self.solution()
        wrong: list[BaseModel] = []
        seen = {self.serialise(right)}
        for state in self.near_misses():
            key = self.serialise(state)
            if key in seen or self.read(key) is None or self.grade_state(state):
                continue
            seen.add(key)
            wrong.append(state)
            if len(wrong) == MOST_CHOICES - 1:
                break
        # Where the right one goes is fixed by the item's own declaration, so it
        # moves from item to item but never between two loads of one.
        seed = self.model_dump_json()
        wrong.sort(key=lambda s: order_key(seed, self.serialise(s)))
        at = int(order_key(seed, "right"), 16) % (len(wrong) + 1)
        options = [*wrong[:at], right, *wrong[at:]]
        return [(self.serialise(s), self.describe(s, locale)) for s in options]

    # --- the base's no-script hooks ---------------------------------------
    #
    # Each option submits a whole state, which `grade` reads as a built board,
    # so a bare string (a typed number, or anything else) is never right here.

    def made_key(self) -> str:
        return "activity.cards.you_placed"

    def typed_right(self, text: str) -> bool:
        return False

    def typed_example(self) -> str:
        """The right option's value -- or nothing, when the choice is not a
        question: fewer than three options, or not exactly one right. The
        item then fails at load as "the no-script answer does not grade"."""
        choices = self.fallback_choices("nb")
        right = [value for value, _ in choices if grade(self, value)]
        if len(choices) < FEWEST_CHOICES or len(right) != 1:
            return ""
        return right[0]

    def typed_compare(self, text: str, locale: str) -> Comparison:
        # Not a state and not one of the options: said plainly, task still drawn.
        made = translate(locale, "activity.unreadable")
        solution = self.solution()
        return Comparison(
            made, made, self.describe(solution, locale), None, self.board(solution, locale)
        )
