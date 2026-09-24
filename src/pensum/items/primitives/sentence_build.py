"""Sentence building: word tiles and punctuation tiles put in order.

*Hvor bor du?* from *du*, *bor*, *hvor* and a question mark; *Yesterday I played
football.* against the Norwegian order *Yesterday played I football.* Word order,
punctuation and the capital letter are one board.

**A capital letter is a tile flip, not a rule of its own.** Tiles are written in
lower case (a name or the English *I* is written as it always is), and tapping a
placed word turns its first letter; putting it back in the tray turns it back.
So a sentence without its capital is a sentence the pupil built and can see,
not a hidden penalty.

Graded on the exact tokens in the frame, gaps closed up, against the declared
`accept` sentences. Each is written as it is spelled, "Hvor bor du?", and split
into tokens the same way a typed answer is, so the author never writes tokens by
hand. Every accepted sentence must be buildable from the tiles in the frame's
places, or the item does not load.

Without a script the pupil types the sentence, which is split into the same
tokens and compared the same way, capital and mark included.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.primitives import tiles
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer, Piece

MAX_TILES = 12
MAX_SLOTS = 10
PER_ROW = 5


class SentenceBuildState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slots: tuple[int, ...]
    # Tiles whose first letter is turned, as tile indices, in ascending order.
    flipped: tuple[int, ...] = ()


def flip(text: str) -> str:
    return text[:1].swapcase() + text[1:]


def flippable(text: str) -> bool:
    return bool(text) and text[0].isalpha() and text[0].swapcase() != text[0]


class SentenceBuildActivity(ActivityConfig):
    """Build one of the `accept` sentences from `words`."""

    FALLBACK_KEY = "activity.sentence_build.ask"
    State = SentenceBuildState

    kind: Literal["sentence_build"] = "sentence_build"
    # Every tile, words and marks: "hvor", "bor", "du", "?".
    words: tuple[str, ...] = Field(min_length=2, max_length=MAX_TILES)
    # Every sentence that is right, as written. The first is the one shown.
    accept: tuple[str, ...] = Field(min_length=1)
    slots: int | None = Field(default=None, ge=2, le=MAX_SLOTS)

    @model_validator(mode="after")
    def _check(self) -> SentenceBuildActivity:
        if self.fallback is not None:
            raise ValueError("sentence_build asks for the sentence typed without a script")
        for word in self.words:
            if tiles.tokens(word) != [word]:
                raise ValueError(f"the tile {word!r} is not one word or one mark")
        for text in self.accept:
            if self._state(tiles.tokens(text)) is None:
                raise ValueError(
                    f"{text!r} cannot be built from {self.words} in {self.frame_size} places"
                )
        return self

    # --- sizes -----------------------------------------------------------------

    @property
    def texts(self) -> tuple[str, ...]:
        return tiles.tray_order(self.words)

    @property
    def frame_size(self) -> int:
        if self.slots is not None:
            return self.slots
        return min(MAX_SLOTS, len(tiles.tokens(self.accept[0])))

    def _state(self, wanted: list[str]) -> SentenceBuildState | None:
        """A frame holding `wanted`, flipping a tile where its turned text fits."""
        if len(wanted) > self.frame_size:
            return None
        free = list(range(len(self.texts)))
        slots: list[int] = []
        flipped: list[int] = []
        for word in wanted:
            plain = next((i for i in free if self.texts[i] == word), None)
            turned = next(
                (i for i in free if flippable(self.texts[i]) and flip(self.texts[i]) == word),
                None,
            )
            pick = plain if plain is not None else turned
            if pick is None:
                return None
            if plain is None:
                flipped.append(pick)
            free.remove(pick)
            slots.append(pick)
        slots += [tiles.EMPTY] * (self.frame_size - len(slots))
        return SentenceBuildState(slots=tuple(slots), flipped=tuple(sorted(flipped)))

    # --- rules -----------------------------------------------------------------

    def built(self, state: SentenceBuildState) -> list[str]:
        return [
            flip(self.texts[s]) if s in state.flipped else self.texts[s]
            for s in state.slots
            if s != tiles.EMPTY
        ]

    def initial(self) -> SentenceBuildState:
        return SentenceBuildState(slots=(tiles.EMPTY,) * self.frame_size)

    def solution(self) -> SentenceBuildState:
        state = self._state(tiles.tokens(self.accept[0]))
        if state is None:  # checked when the item loaded, so never in practice
            raise ValueError("the first accepted sentence cannot be built")
        return state

    def admits(self, state: SentenceBuildState) -> bool:
        if not tiles.valid(state.slots, self.frame_size, len(self.texts)):
            return False
        placed = set(state.slots)
        return (
            list(state.flipped) == sorted(set(state.flipped))
            and all(i in placed and i != tiles.EMPTY for i in state.flipped)
            and all(flippable(self.texts[i]) for i in state.flipped)
        )

    def _right(self, words: list[str]) -> bool:
        return any(words == tiles.tokens(text) for text in self.accept)

    def grade_state(self, state: SentenceBuildState) -> bool:
        return self._right(self.built(state))

    def default_fallback(self) -> float:
        return 0.0

    def describe(self, state: SentenceBuildState, locale: str) -> str:
        words = self.built(state)
        if not words:
            return translate(locale, "activity.sentence_build.empty")
        return translate(locale, "activity.sentence_build.made", sentence=tiles.sentence(words))

    def limits(self) -> dict[str, object]:
        return {
            "slots": self.frame_size,
            "tiles": list(self.texts),
            "marks": sorted(tiles.PUNCTUATION),
        }

    def say(self, locale: str) -> dict[str, str]:
        return {
            "made": translate(locale, "activity.sentence_build.made"),
            "empty": translate(locale, "activity.sentence_build.empty"),
        }

    # --- the no-script road ----------------------------------------------------

    def typed_right(self, text: str) -> bool:
        return self._right(tiles.tokens(text))

    def typed_example(self) -> str:
        return self.accept[0]

    def typed_compare(self, text: str, locale: str) -> Comparison:
        words = tiles.tokens(text)
        made = tiles.sentence(words) or "—"
        asked = tiles.sentence(tiles.tokens(self.accept[0]))
        state = self._state(words) if words else None
        return Comparison(
            translate(locale, "activity.you_wrote", made=made, asked=asked),
            made,
            asked,
            self.board(state, locale) if state else None,
            self.board(self.solution(), locale),
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: SentenceBuildState, locale: str) -> Board:
        # A turned tile is drawn as its own piece text, so the frame shows the
        # capital exactly as it will be graded. Every tile is drawn twice in each
        # slot, plain and turned, and the state picks which one shows.
        texts = self.texts
        left = top = tiles.MARGIN
        slot_w = tiles.tile_width(texts) + 6
        zones, plain, width, bottom = tiles.frame(
            state.slots, texts, left=left, top=top, slot_w=slot_w, per_row=PER_ROW
        )
        pieces = []
        for piece in plain:
            t = piece.index
            turned = t in state.flipped
            pieces.append(
                tiles.tile(
                    piece.zone, t, piece.x, piece.y, piece.w, texts[t], piece.shown and not turned
                )
            )
            if flippable(texts[t]):
                pieces.append(
                    Piece(
                        piece.zone,
                        t,
                        "tile",
                        piece.x,
                        piece.y,
                        piece.w,
                        piece.h,
                        piece.shown and turned,
                        label=flip(texts[t]),
                        row=1,
                    )
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
