"""Gangetabellen: the hundred facts from 1 · 1 to 10 · 10, and which a pupil knows.

A cell of the table is one fact. It has not been asked, or the pupil's latest
answer to it was right, or it was not. A round asks for the cells not asked
yet, in no order, until every cell has been; after that, and whenever the pupil
chooses to, it asks for the ones not known yet.

The answer is typed, not picked. In the item shape that is a pick among the
numbers from 0 to 100: the candidate's index is the number typed.

Where a pupil is signed in the table is read from their evidence. Where nobody
is, it rides in the address, as the year does: a hundred characters, one a
cell.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from random import Random

from pensum.arkade.arithmetic import MULTIPLY, TABLES, Fact
from pensum.arkade.items import Item
from pensum.arkade.rounds import Marked
from pensum.scores.evidence import Evidence

SIZE = 10
UNASKED, KNOWN, NOT_YET = "0", "1", "2"
STATES = {UNASKED: "unasked", KNOWN: "known", NOT_YET: "not_yet"}

# What can be typed: every product in the table, and every number a wrong
# answer could plausibly be.
TYPEABLE = tuple(str(n) for n in range(SIZE * SIZE + 1))

# Apart from the balloons' `mat:7·8`: a balloon asks whether a product shown is
# right, and that is not the same as producing it.
PREFIX = "gange:"
SKILL = TABLES.skill

Cell = tuple[int, int]
CELLS: tuple[Cell, ...] = tuple((a, b) for a in range(1, SIZE + 1) for b in range(1, SIZE + 1))


def item_for(cell: Cell) -> Item:
    fact = Fact(cell[0], MULTIPLY, cell[1])
    return Item(
        id=PREFIX + fact.key,
        rule="times",
        candidates=TYPEABLE,
        matches=frozenset({fact.value}),
        answer=fact.statement(),
        skill=SKILL,
        shown=fact.expression,
    )


def cell_of(item_id: str) -> Cell | None:
    """The cell an item id names, or None for any other item."""
    if not item_id.startswith(PREFIX):
        return None
    a, _, b = item_id.removeprefix(PREFIX).partition(MULTIPLY)
    if not (a.isdigit() and b.isdigit()):
        return None
    cell = (int(a), int(b))
    return cell if cell in CELLS else None


@dataclass(frozen=True)
class Table:
    """What a pupil knows of the table: a state for each cell that has been asked."""

    asked: dict[Cell, str]

    def state(self, cell: Cell) -> str:
        return self.asked.get(cell, UNASKED)

    def cells(self, state: str) -> list[Cell]:
        return [cell for cell in CELLS if self.state(cell) == state]

    def count(self, state: str) -> int:
        return len(self.cells(state))

    def rows(self) -> list[list[dict[str, object]]]:
        """The table as a page draws it: ten rows of ten cells."""
        return [
            [
                {"a": a, "b": b, "value": a * b, "state": STATES[self.state((a, b))]}
                for b in range(1, SIZE + 1)
            ]
            for a in range(1, SIZE + 1)
        ]

    @property
    def text(self) -> str:
        """The table as it rides in an address."""
        return "".join(self.state(cell) for cell in CELLS)

    def after(self, marked: Iterable[Marked]) -> Table:
        """The table once a round's answers are in. An unanswered cell keeps its state."""
        asked = dict(self.asked)
        for m in marked:
            cell = cell_of(m.item.id)
            if cell is not None and m.correct is not None:
                asked[cell] = KNOWN if m.correct else NOT_YET
        return Table(asked)

    def questions(self, rng: Random, count: int, *, drill: bool = False) -> list[Item]:
        """A round of up to `count` cells, no cell twice.

        Cells not asked yet come first, so every cell is asked before any is
        asked again; then the ones not known yet, then the known ones. A drill
        is only the cells not known yet, however few.
        """
        tiers = (
            [self.cells(NOT_YET)] if drill else [self.cells(s) for s in (UNASKED, NOT_YET, KNOWN)]
        )
        picked: list[Cell] = []
        for tier in tiers:
            rng.shuffle(tier)
            picked += tier[: count - len(picked)]
        # In no order: the cells topping a round up are not all at its end.
        rng.shuffle(picked)
        return [item_for(cell) for cell in picked]


def from_text(text: str) -> Table:
    """The table an address carries. Anything that is not one is an empty table."""
    if len(text) != len(CELLS) or set(text) - set(STATES):
        return Table({})
    return Table({cell: state for cell, state in zip(CELLS, text, strict=True) if state != UNASKED})


def from_evidence(rows: Iterable[Evidence]) -> Table:
    """The table a pupil's evidence shows: for each cell, the latest answer to it."""
    asked: dict[Cell, str] = {}
    for row in sorted(rows, key=lambda row: row.recorded_at):
        cell = cell_of(row.item)
        if cell is not None:
            asked[cell] = KNOWN if row.correct else NOT_YET
    return Table(asked)
