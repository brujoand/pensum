"""Sound boxes: hear a word, push a counter into a box for each sound.

Elkonin boxes, the step that separates hearing sounds from spelling them. The
browser says the word (its own speech voice, as the listening exercise does:
nothing is fetched, nothing is recorded), and the pupil pushes one counter into
a row of boxes for each sound they hear: *sol* is three, *kjole* is four,
because *kj* is one sound. When the item asks for it, they then drag letter
tiles onto the counters, one sound to a box.

There are always more boxes than sounds. A row of exactly three boxes would
answer "how many sounds?" before the word was heard.

Graded on the count first, then the letters: `sounds` is the word as the pupil
should split it, one entry per sound, and a letter tile is right in a box when
its text is that box's sound. The word itself is never shown on the board while
there is a voice to say it; if the browser has none for the item's language,
the page says so and shows the word written, because counting the sounds of a
written word is still the exercise and guessing at a silent one is not. The
written word's element is rendered empty and the page's script fills it in only
once it has looked for a voice and found none.

The word is still in the page source, in `limits()["word"]` (and in the no-script
question, which the script hides): the browser voice speaks it from text, so the
page has to have it. That is a trade-off, not an oversight. What the rule above
guarantees is that nothing *shows* the word while there is a voice to say it.

Without a script the pupil sees the word written and types how many sounds it
has.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.i18n import translate
from pensum.items.figures import Label
from pensum.items.primitives import tiles
from pensum.items.primitives.base import (
    ActivityConfig,
    Board,
    Layer,
    Piece,
    Zone,
    plural,
    say_keys,
)

MAX_SOUNDS = 8
MAX_EXTRA = 4
MIN_BOXES = 5
SPARE_BOXES = 2
COUNTER_R = 8.0
# The counter sits in the top of its box and the letter under it.
COUNTER_BAND = 26.0


class SoundBoxesState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    counters: int = Field(ge=0)
    slots: tuple[int, ...]


class SoundBoxesActivity(ActivityConfig):
    """A counter in a box for each sound of `word`, then optionally its letters."""

    FALLBACK_KEY = "activity.sound_boxes.ask"
    State = SoundBoxesState

    kind: Literal["sound_boxes"] = "sound_boxes"
    word: str = Field(min_length=1)
    # The language the browser voice says the word in.
    language: Literal["nb", "en"]
    # The word split into its sounds, each written as the letters that spell it.
    sounds: tuple[str, ...] = Field(min_length=1, max_length=MAX_SOUNDS)
    # Whether the letters go into the boxes too, after the counters.
    letters: bool = False
    # Letter tiles that belong to no box: the near misses worth offering.
    extra: tuple[str, ...] = Field(default=(), max_length=MAX_EXTRA)

    @model_validator(mode="after")
    def _check(self) -> SoundBoxesActivity:
        if self.fallback is not None:
            raise ValueError("sound_boxes asks for the number of sounds without a script")
        if any(not s.strip() or s != s.strip() for s in self.sounds + self.extra):
            raise ValueError("a sound is written as its letters, with no spaces")
        if self.extra and not self.letters:
            raise ValueError("extra letter tiles need letters: true")
        if self.letters and "".join(self.sounds).casefold() != self.word.casefold():
            raise ValueError(
                f"the sounds {self.sounds} do not spell {self.word!r}; with letters "
                "the boxes spell the word, so every letter must be in one"
            )
        return self

    # --- sizes -----------------------------------------------------------------

    @property
    def capacity(self) -> int:
        return max(MIN_BOXES, len(self.sounds) + SPARE_BOXES)

    @property
    def texts(self) -> tuple[str, ...]:
        return tiles.tray_order(self.sounds + self.extra) if self.letters else ()

    # --- rules -----------------------------------------------------------------

    def initial(self) -> SoundBoxesState:
        return SoundBoxesState(counters=0, slots=(tiles.EMPTY,) * self.capacity)

    def solution(self) -> SoundBoxesState:
        n = len(self.sounds)
        if not self.letters:
            return SoundBoxesState(counters=n, slots=(tiles.EMPTY,) * self.capacity)
        slots = tiles.fill(self.texts, self.sounds, self.capacity)
        if slots is None:  # the sounds are always in the tray
            raise ValueError("the sounds are not all in the tray")
        return SoundBoxesState(counters=n, slots=slots)

    def admits(self, state: SoundBoxesState) -> bool:
        if state.counters > self.capacity:
            return False
        return tiles.valid(state.slots, self.capacity, len(self.texts), usable=state.counters)

    def grade_state(self, state: SoundBoxesState) -> bool:
        n = len(self.sounds)
        if state.counters != n:
            return False
        if not self.letters:
            return True
        return [self.texts[s] if s != tiles.EMPTY else "" for s in state.slots[:n]] == list(
            self.sounds
        )

    def default_fallback(self) -> float:
        return float(len(self.sounds))

    def from_number(self, value: float) -> SoundBoxesState | None:
        if not float(value).is_integer() or not 0 <= value <= self.capacity:
            return None
        return SoundBoxesState(counters=int(value), slots=(tiles.EMPTY,) * self.capacity)

    def fallback_prompt(self, locale: str) -> str:
        return translate(locale, self.FALLBACK_KEY, word=self.word)

    def describe(self, state: SoundBoxesState, locale: str) -> str:
        text = plural(locale, "activity.sound_boxes.made", state.counters)
        if self.letters and state.counters:
            text += ": " + _letters(state, self.texts)
        return text

    def limits(self) -> dict[str, object]:
        return {
            "capacity": self.capacity,
            "tiles": list(self.texts),
            "letters": self.letters,
            "language": self.language,
            "word": self.word,
        }

    def say(self, locale: str) -> dict[str, str]:
        return say_keys(
            locale,
            "activity.sound_boxes.made",
            "activity.sound_boxes.made_one",
            "activity.sound_boxes.written",
        )

    # --- drawing -----------------------------------------------------------------

    def board(self, state: SoundBoxesState, locale: str) -> Board:
        texts = self.texts
        tile_w = tiles.tile_width(texts) if texts else tiles.TILE_MIN_W
        box_w = tile_w + 10
        box_h = COUNTER_BAND + (tiles.TILE_H + 8 if self.letters else 0)
        left = top = tiles.MARGIN
        zones, pieces, width, bottom = tiles.frame(
            state.slots,
            texts,
            left=left,
            top=top,
            slot_w=box_w,
            slot_h=box_h,
            per_row=self.capacity,
            tile_top=COUNTER_BAND,
        )
        zones = [Zone(z.name, z.x, z.y, z.w, z.h, z.index, "zone slot box") for z in zones]
        for i, zone in enumerate(zones):
            pieces.append(
                Piece(
                    "counters",
                    i,
                    "counter",
                    zone.x + zone.w / 2 - COUNTER_R,
                    zone.y + COUNTER_BAND / 2 - COUNTER_R + 2,
                    2 * COUNTER_R,
                    2 * COUNTER_R,
                    i < state.counters,
                )
            )

        # The box of spare counters, where a counter comes from and goes back to.
        y = bottom + tiles.MARGIN
        supply_w = 2 * COUNTER_R + 16
        zones.append(Zone("supply", left, y, supply_w, supply_w, role="zone tray"))
        pieces.append(
            Piece(
                "supply",
                0,
                "counter",
                left + 8,
                y + 8,
                2 * COUNTER_R,
                2 * COUNTER_R,
            )
        )
        labels = [
            Label(
                left + supply_w + 8,
                y + supply_w / 2,
                translate(locale, "activity.sound_boxes.supply"),
                size=11,
                anchor="start",
            )
        ]
        layers = [Layer("base", (), tuple(zones), tuple(pieces), tuple(labels))]
        bottom = y + supply_w
        if texts:
            tray, tray_w, bottom = tiles.tray(
                state.slots,
                texts,
                left=left,
                top=bottom,
                label=translate(locale, "activity.tiles.tray"),
            )
            layers.append(tray)
            width = max(width, tray_w)
        return Board(width + 2 * left, bottom + tiles.MARGIN, self.alt.get(locale), tuple(layers))


def _letters(state: SoundBoxesState, texts: tuple[str, ...]) -> str:
    """The boxes with counters in them, as letters: "s-o-_"."""
    return "-".join(texts[s] if s != tiles.EMPTY else "_" for s in state.slots[: state.counters])
