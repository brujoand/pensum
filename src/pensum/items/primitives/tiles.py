"""Tiles dragged into a frame: what the language primitives share.

Sound boxes put letters in boxes, a word frame takes letters, syllables or
morphemes, and a sentence frame takes words and punctuation. Underneath, all
three are the same board: a row of numbered slots, a tray of tiles, and a state
that says which tile sits in which slot. It is written once, here, so the three
cannot drift on what a move means or on what a malformed state is.

**The tray is sorted, not authored.** Tiles are laid out in alphabetical order
(punctuation first), whatever order the author listed them in, because a list
written by someone who knows the answer is usually written in the answer's
order, and then the tray gives the word away.

**A slot holds one tile and a tile is in one place.** The state is a tuple of
tile indices, one per slot, with -1 for an empty slot; a tile appearing twice
is a state no board could have produced, so it is refused. Two tiles may carry
the same text (the two *a*s in *mamma*): they are two tiles, and grading reads
the text, so either one is right.

The unused tiles are drawn in their own layer, with the role `tray`, so the
feedback can leave them out: they are part of the question, not of what the
pupil built.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence

from pensum.items.figures import Label
from pensum.items.primitives.base import Layer, Piece, Zone

EMPTY = -1
# A tile is sized for its longest text, and every tile is the same size, so a
# long morpheme does not read as a more important one.
CHAR_W = 9.0
TILE_PAD = 16.0
TILE_MIN_W = 34.0
TILE_H = 34.0
GAP = 8.0
MARGIN = 12.0
TRAY_PER_ROW = 6
# How far below the frame the tray starts: room for its label.
TRAY_GAP = 26.0

# Punctuation a sentence frame knows. Written straight after the word before
# it, never with a space: "du?" and not "du ?".
PUNCTUATION = frozenset(".,!?:;")

# One token of a typed sentence: a word, apostrophes and hyphens included, or a
# single mark. "Don't stop!" is ["Don't", "stop", "!"].
_TOKEN = re.compile(r"[\w'’-]+|[^\w\s]")


def nfc(text: str) -> str:
    """One spelling of å: typed on a phone it may arrive decomposed."""
    return unicodedata.normalize("NFC", text)


def tokens(text: str) -> list[str]:
    """A typed sentence as the tiles it would be built from."""
    return _TOKEN.findall(nfc(text))


def sentence(words: Sequence[str]) -> str:
    """Tokens joined the way they are written: marks against the word before."""
    out = ""
    for word in words:
        if out and word not in PUNCTUATION:
            out += " "
        out += word
    return out


def mix(*parts: str) -> str:
    """A stable, unguessable sort key: choices shown in an order that is the
    same on every reload and is not the order the author wrote them in, for the
    reason `QuizItem.display_choices` gives."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def tray_order(texts: Sequence[str]) -> tuple[str, ...]:
    """The tiles in the order the tray shows them. See the module docstring."""
    return tuple(sorted(texts, key=lambda t: (t not in PUNCTUATION, t.casefold(), t)))


def valid(slots: Sequence[int], count: int, tiles: int, usable: int | None = None) -> bool:
    """Whether a slot tuple could have come off a frame of `count` slots.

    `usable` limits which slots may hold a tile at all: in sound boxes, a letter
    goes only in a box that has a counter in it.
    """
    if len(slots) != count:
        return False
    placed = [s for s in slots if s != EMPTY]
    if any(s < EMPTY or s >= tiles for s in slots):
        return False
    if len(set(placed)) != len(placed):
        return False
    if usable is not None:
        return all(s == EMPTY for s in slots[usable:])
    return True


def built(slots: Sequence[int], texts: Sequence[str]) -> list[str]:
    """The texts in the frame, in order, gaps closed up."""
    return [texts[s] for s in slots if s != EMPTY]


def fill(texts: Sequence[str], wanted: Sequence[str], count: int) -> tuple[int, ...] | None:
    """Slots holding tiles whose texts are `wanted`, in order; None if the tray
    does not have them. Used to draw an accepted answer, and a typed one."""
    free = list(range(len(texts)))
    slots: list[int] = []
    for word in wanted:
        match = next((i for i in free if texts[i] == word), None)
        if match is None:
            return None
        free.remove(match)
        slots.append(match)
    if len(slots) > count:
        return None
    return tuple(slots) + (EMPTY,) * (count - len(slots))


def tile_width(texts: Sequence[str]) -> float:
    longest = max((len(t) for t in texts), default=1)
    return max(TILE_MIN_W, longest * CHAR_W + TILE_PAD)


def tile(zone: str, index: int, x: float, y: float, w: float, text: str, shown: bool) -> Piece:
    return Piece(zone, index, "tile", x, y, w, TILE_H, shown, label=text)


def frame(
    slots: Sequence[int],
    texts: Sequence[str],
    *,
    left: float,
    top: float,
    slot_w: float,
    slot_h: float = TILE_H + 8,
    per_row: int = 8,
    tile_top: float = 4.0,
) -> tuple[list[Zone], list[Piece], float, float]:
    """The slots, and every tile that could sit in each one.

    Every tile is drawn in every slot and only the one there is shown, because
    the page shows and hides pieces the server placed rather than moving them.
    Returns the zones, the pieces, and the width and bottom edge of the frame.
    """
    zones: list[Zone] = []
    pieces: list[Piece] = []
    tw = tile_width(texts)
    right = left
    bottom = top
    for i, held in enumerate(slots):
        row, col = divmod(i, per_row)
        x = left + col * (slot_w + GAP)
        y = top + row * (slot_h + GAP)
        zones.append(Zone(f"s{i}", x, y, slot_w, slot_h, index=i, role="zone slot"))
        for t, text in enumerate(texts):
            pieces.append(
                tile(f"s{i}", t, x + (slot_w - tw) / 2, y + tile_top, tw, text, held == t)
            )
        right = max(right, x + slot_w)
        bottom = max(bottom, y + slot_h)
    return zones, pieces, right - left, bottom


def tray(
    slots: Sequence[int], texts: Sequence[str], *, left: float, top: float, label: str
) -> tuple[Layer, float, float]:
    """The unused tiles, in their own layer. Returns it, its width and bottom."""
    used = {s for s in slots if s != EMPTY}
    tw = tile_width(texts)
    rows = max(1, -(-len(texts) // TRAY_PER_ROW))
    cols = min(len(texts), TRAY_PER_ROW)
    width = cols * (tw + GAP) + GAP
    height = rows * (TILE_H + GAP) + GAP
    y0 = top + TRAY_GAP
    zone = Zone("tray", left, y0, width, height, role="zone tray")
    pieces = []
    for t, text in enumerate(texts):
        row, col = divmod(t, TRAY_PER_ROW)
        pieces.append(
            tile(
                "tray",
                t,
                left + GAP + col * (tw + GAP),
                y0 + GAP + row * (TILE_H + GAP),
                tw,
                text,
                t not in used,
            )
        )
    caption = Label(left, top + TRAY_GAP / 2, label, size=11, anchor="start")
    layer = Layer("tray", (), (zone,), tuple(pieces), (caption,))
    return layer, width, y0 + height


__all__ = [
    "EMPTY",
    "MARGIN",
    "PUNCTUATION",
    "built",
    "fill",
    "mix",
    "frame",
    "nfc",
    "sentence",
    "tile_width",
    "tokens",
    "tray",
    "tray_order",
    "valid",
]
