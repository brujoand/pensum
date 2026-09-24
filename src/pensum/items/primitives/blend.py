"""Blending: letter tiles slid together, then the word they make picked.

The sound slide from `docs/design/subjects/norsk.md`. Tiles *s*, *o*, *l* sit
apart; touching one says its sound, sliding them together one at a time joins
them, and when the last is on, the pupil picks what the word means from a few
choices. A grapheme that is one sound is one tile -- *sh*, *ch*, *th* in
English, *kj* and *skj* in Norwegian -- because splitting *sh* into *s* and *h*
teaches the wrong sounds.

**What is spoken.** The browser's own speech voice says each tile, either the
tile's letters or the item's `say` for it where the letters alone would be
read as a letter name ("sss" for *s*). When `say_word` is on, the joined word
is said once too. Nothing is recorded and nothing is fetched. If the browser has
no voice for the item's language the page says so and the slide works as
letters only, the same stance the listening exercise takes: a wrong-language
voice would say a different word, not the same one badly.

**The choices are meanings, not spellings.** Picking the written word after
hearing it would test matching, not decoding. So a choice is a short gloss or a
translation ("et skip" for *ship*), and for a Norwegian decoding item the item
can switch `say_word` off so that blending is left to the pupil.

Graded on the pick. Joining is the scaffold, not the answer, but a pick is only
possible once every tile is on the slide, so a state with a pick and a gap is
one no board produced and is refused. Without a script the tiles are drawn as
letters and the pupil picks from the same choices as radio buttons.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label
from pensum.items.primitives import tiles
from pensum.items.primitives.base import ActivityConfig, Board, Comparison, Layer, Piece, Zone
from pensum.items.text import AuthoredText

MAX_TILES = 6
SPREAD = 22.0
PICK_H = 30.0


class BlendTile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # The grapheme as written: "s", "sh", "skj".
    text: str = Field(min_length=1, max_length=4)
    # What the voice says for it, where the letters would be read as a name.
    say: str | None = None


class BlendChoice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=8, pattern=r"^[a-z0-9]+$")
    text: AuthoredText


class BlendState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # How many tiles are on the slide, from the left.
    joined: int = Field(ge=0)
    # The id of the picked choice, or "" for none yet.
    pick: str = ""


class BlendActivity(ActivityConfig):
    FALLBACK_KEY = "activity.blend.ask"
    State = BlendState

    kind: Literal["blend"] = "blend"
    language: Literal["nb", "en"]
    tiles: tuple[BlendTile, ...] = Field(min_length=2, max_length=MAX_TILES)
    # Whether the voice says the whole word once the last tile is on.
    say_word: bool = True
    choices: tuple[BlendChoice, ...] = Field(min_length=2, max_length=4)
    answer: str

    @model_validator(mode="after")
    def _check(self) -> BlendActivity:
        if self.fallback is not None:
            raise ValueError("blend asks for the same pick without a script")
        ids = [c.id for c in self.choices]
        if len(set(ids)) != len(ids):
            raise ValueError("choice ids must be unique")
        if self.answer not in ids:
            raise ValueError(f"the answer {self.answer!r} is not one of the choices {ids}")
        return self

    @property
    def word(self) -> str:
        return "".join(t.text for t in self.tiles)

    def shown_choices(self) -> list[BlendChoice]:
        """The choices in the order the page lists them."""
        return sorted(self.choices, key=lambda c: tiles.mix(self.word, c.id))

    def _choice(self, pick: str) -> BlendChoice | None:
        return next((c for c in self.choices if c.id == pick), None)

    # --- rules -----------------------------------------------------------------

    def initial(self) -> BlendState:
        return BlendState(joined=0)

    def solution(self) -> BlendState:
        return BlendState(joined=len(self.tiles), pick=self.answer)

    def admits(self, state: BlendState) -> bool:
        if state.joined > len(self.tiles):
            return False
        if state.pick:
            return state.joined == len(self.tiles) and self._choice(state.pick) is not None
        return True

    def grade_state(self, state: BlendState) -> bool:
        return state.pick == self.answer

    def default_fallback(self) -> float:
        return 0.0

    def describe(self, state: BlendState, locale: str) -> str:
        choice = self._choice(state.pick)
        if choice is None:
            return translate(locale, "activity.blend.none")
        return translate(locale, "activity.blend.made", choice=choice.text.get(locale))

    def made_key(self) -> str:
        return "activity.blend.you_picked"

    def limits(self) -> dict[str, object]:
        return {
            "count": len(self.tiles),
            "choices": [c.id for c in self.choices],
            "language": self.language,
            "sounds": [t.say or t.text for t in self.tiles],
            "word": self.word if self.say_word else "",
        }

    def say(self, locale: str) -> dict[str, str]:
        texts = {f"choice_{c.id}": c.text.get(locale) for c in self.choices}
        return {
            "made": translate(locale, "activity.blend.made"),
            "none": translate(locale, "activity.blend.none"),
            **texts,
        }

    # --- the no-script road ----------------------------------------------------

    def typed_right(self, text: str) -> bool:
        return text.strip() == self.answer

    def typed_example(self) -> str:
        return self.answer

    def typed_compare(self, text: str, locale: str) -> Comparison:
        pick = text.strip()
        state = BlendState(joined=len(self.tiles), pick=pick)
        made = self.describe(state, locale)
        asked = self.describe(self.solution(), locale)
        drawn = self.board(state, locale) if self._choice(pick) else None
        return Comparison(
            translate(locale, self.made_key(), made=made, asked=asked),
            made,
            asked,
            drawn,
            self.board(self.solution(), locale),
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: BlendState, locale: str) -> Board:
        texts = [t.text for t in self.tiles]
        tw = tiles.tile_width(texts)
        n = len(texts)
        left = top = tiles.MARGIN
        # The slide on top, where tiles sit touching; the tiles apart below it.
        slide_w = n * tw + 8
        apart_w = n * tw + (n - 1) * SPREAD + 8
        width = max(slide_w, apart_w)
        slide = Zone("joined", left, top, width, tiles.TILE_H + 8, role="zone slide")
        apart_y = top + tiles.TILE_H + 8 + 14
        apart = Zone("apart", left, apart_y, width, tiles.TILE_H + 8, role="zone slot")
        pieces: list[Piece] = []
        for i, text in enumerate(texts):
            pieces.append(
                tiles.tile("joined", i, left + 4 + i * tw, top + 4, tw, text, i < state.joined)
            )
            pieces.append(
                tiles.tile(
                    "apart",
                    i,
                    left + 4 + i * (tw + SPREAD),
                    apart_y + 4,
                    tw,
                    text,
                    i >= state.joined,
                )
            )
        # The pick, drawn as a card under the tiles: one card per choice, the
        # picked one shown, so the feedback can draw what was chosen.
        pick_y = apart_y + tiles.TILE_H + 8 + 14
        labels = [
            Label(
                left,
                pick_y + PICK_H / 2,
                translate(locale, "activity.blend.picked"),
                size=11,
                anchor="start",
            )
        ]
        card_x = left + 64
        longest = max(len(c.text.get(locale)) for c in self.choices)
        card_w = max(80.0, longest * 7.5 + 16)
        for i, choice in enumerate(self.choices):
            pieces.append(
                Piece(
                    "pick",
                    i,
                    "card",
                    card_x,
                    pick_y,
                    card_w,
                    PICK_H,
                    choice.id == state.pick,
                    label=choice.text.get(locale),
                )
            )
        width = max(width, 64 + card_w)
        return Board(
            width + 2 * left,
            pick_y + PICK_H + tiles.MARGIN,
            self.alt.get(locale),
            (Layer("base", (), (slide, apart), tuple(pieces), tuple(labels)),),
        )
