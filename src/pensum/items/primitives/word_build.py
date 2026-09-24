"""Word building: letters, syllables or morphemes dragged into a word frame.

*fotball* from *fot* + *ball*, *hoppet* from *hopp* + *et*, *takk* from its
letters. Compounds, inflections and spelling are the same action, which is why
they are one primitive: the pupil puts pieces in order and the frame reads what
they spell.

Graded on the word the frame spells, gaps closed up, against every form the
item declares in `accept`. Case is ignored -- a capital is not what this board
tests, and `sentence_build` is where it is. Every accepted form must be
buildable from the declared tiles in the declared number of slots, so an item
that cannot be answered fails when it loads rather than in front of a child.

Without a script the pupil types the word, and the typed word is graded against
the same list.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.primitives import tiles
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer

MAX_TILES = 12
MAX_SLOTS = 10


class WordBuildState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slots: tuple[int, ...]


class WordBuildActivity(ActivityConfig):
    """Build one of the `accept` words from `parts` in a frame of `slots`."""

    FALLBACK_KEY = "activity.word_build.ask"
    State = WordBuildState

    kind: Literal["word_build"] = "word_build"
    # Every tile on offer: the pieces of the word and any near misses.
    parts: tuple[str, ...] = Field(min_length=2, max_length=MAX_TILES)
    # Every spelling that is right. The first is the one feedback shows.
    accept: tuple[str, ...] = Field(min_length=1)
    # How many places the frame has. Defaults to the number of tiles the first
    # accepted word takes, which is a hint; set it higher to withhold it.
    slots: int | None = Field(default=None, ge=1, le=MAX_SLOTS)

    @model_validator(mode="after")
    def _check(self) -> WordBuildActivity:
        if self.fallback is not None:
            raise ValueError("word_build asks for the word typed without a script")
        if any(not p.strip() or p != p.strip() for p in self.parts):
            raise ValueError("a tile is its text, with no spaces around it")
        for word in self.accept:
            if self._split(word) is None:
                raise ValueError(
                    f"{word!r} cannot be built from {self.parts} in {self.frame_size} places"
                )
        return self

    # --- sizes -----------------------------------------------------------------

    @property
    def texts(self) -> tuple[str, ...]:
        return tiles.tray_order(self.parts)

    @property
    def frame_size(self) -> int:
        if self.slots is not None:
            return self.slots
        first = _split(self.texts, self.accept[0], MAX_SLOTS)
        return len(first) if first else MAX_SLOTS

    def _split(self, word: str) -> tuple[int, ...] | None:
        found = _split(self.texts, word, self.frame_size)
        if found is None:
            return None
        return found + (tiles.EMPTY,) * (self.frame_size - len(found))

    # --- rules -----------------------------------------------------------------

    def word(self, state: WordBuildState) -> str:
        return "".join(tiles.built(state.slots, self.texts))

    def initial(self) -> WordBuildState:
        return WordBuildState(slots=(tiles.EMPTY,) * self.frame_size)

    def solution(self) -> WordBuildState:
        slots = self._split(self.accept[0])
        if slots is None:  # checked when the item loaded, so never in practice
            raise ValueError("the first accepted word cannot be built")
        return WordBuildState(slots=slots)

    def admits(self, state: WordBuildState) -> bool:
        return tiles.valid(state.slots, self.frame_size, len(self.texts))

    def grade_state(self, state: WordBuildState) -> bool:
        return self._right(self.word(state))

    def _right(self, word: str) -> bool:
        wanted = {tiles.nfc(w).casefold() for w in self.accept}
        return tiles.nfc(word).strip().casefold() in wanted

    def default_fallback(self) -> float:
        return 0.0

    def describe(self, state: WordBuildState, locale: str) -> str:
        word = self.word(state)
        if not word:
            return translate(locale, "activity.word_build.empty")
        return translate(locale, "activity.word_build.made", word=word)

    def limits(self) -> dict[str, object]:
        return {"slots": self.frame_size, "tiles": list(self.texts)}

    def say(self, locale: str) -> dict[str, str]:
        return {
            "made": translate(locale, "activity.word_build.made"),
            "empty": translate(locale, "activity.word_build.empty"),
        }

    # --- the no-script road ----------------------------------------------------

    def typed_right(self, text: str) -> bool:
        return self._right(text)

    def typed_example(self) -> str:
        return self.accept[0]

    def typed_compare(self, text: str, locale: str) -> Comparison:
        made = tiles.nfc(text).strip() or "—"
        asked = self.accept[0]
        slots = self._split(made.casefold()) if made != "—" else None
        drawn = self.board(WordBuildState(slots=slots), locale) if slots else None
        return Comparison(
            translate(locale, "activity.you_wrote", made=made, asked=asked),
            made,
            asked,
            drawn,
            self.board(self.solution(), locale),
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: WordBuildState, locale: str) -> Board:
        texts = self.texts
        left = top = tiles.MARGIN
        zones, pieces, width, bottom = tiles.frame(
            state.slots,
            texts,
            left=left,
            top=top,
            slot_w=tiles.tile_width(texts) + 6,
            per_row=MAX_SLOTS,
        )
        tray, tray_w, bottom = tiles.tray(
            state.slots,
            texts,
            left=left,
            top=bottom,
            label=translate(locale, "activity.tiles.tray"),
        )
        return Board(
            max(width, tray_w) + 2 * left,
            bottom + tiles.MARGIN,
            self.alt.get(locale),
            (Layer("base", (), tuple(zones), tuple(pieces)), tray),
        )


def _split(texts: tuple[str, ...], word: str, limit: int) -> tuple[int, ...] | None:
    """Distinct tiles, at most `limit`, that spell `word` in order, or None.

    A small search, not a greedy match: with tiles *fot*, *fotb* and *ball*,
    greedy takes *fotb* and is left with *all*.
    """
    target = tiles.nfc(word).casefold()
    folded = [t.casefold() for t in texts]

    def search(rest: str, used: tuple[int, ...]) -> tuple[int, ...] | None:
        if not rest:
            return used
        if len(used) >= limit:
            return None
        for i, text in enumerate(folded):
            if i not in used and rest.startswith(text):
                found = search(rest[len(text) :], (*used, i))
                if found is not None:
                    return found
        return None

    return search(target, ()) if target else None
