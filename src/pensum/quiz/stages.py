"""Stepping down a stage: the same goal, shown more concretely.

Principle 1 orders every skill concrete, then pictorial, then abstract, and
architecture.md's session engine uses that order in reverse after an error: "a
wrong abstract answer is followed by the same target at the pictorial stage,
not by a harder or a different one." Two things in a run do that -- the core
after a wrong answer, and the hint ladder's third step -- and both ask this one
function which item to step to, so they cannot disagree.

Apart from `shape` so the session can import it: `shape` builds on `scoring`,
which already imports the session.
"""

from __future__ import annotations

from collections.abc import Iterable

from pensum.items.schema import QuizItem

# Principle 1's order. A lower rank is a more concrete representation, and
# stepping down moves towards zero.
STAGE_RANK = {"concrete": 0, "pictorial": 1, "abstract": 2}


def lower_stage(item: QuizItem, pool: Iterable[QuizItem], spent: set[str]) -> QuizItem | None:
    """The same goal one stage more concrete, or None.

    Only for an item that declares its stage: an item with none has said
    nothing about representation, and guessing would step it somewhere its
    author never meant. The nearest lower stage wins (abstract steps to
    pictorial before concrete), then the easier item. Anything in `spent` --
    already in the run, or offered at its finish -- is never served twice.
    """
    if item.stage is None:
        return None
    rank = STAGE_RANK[item.stage]
    below = [
        other
        for other in pool
        if other.goal == item.goal
        and other.stage is not None
        and STAGE_RANK[other.stage] < rank
        and other.id not in spent
        and other.id != item.id
    ]
    if not below:
        return None
    return min(below, key=lambda o: (-STAGE_RANK[str(o.stage)], o.difficulty, o.id))
