"""Arithmetic statements, true and false, generated for a pupil's year.

Nothing here is authored. A fact is two numbers and an operation; its false
version is a mistake a pupil plausibly makes with it: one off, ten off, the
neighbouring row of the times table, or `5 : 1 = 1`. A false statement that
nobody would believe is a free point, not a drill.

Written the way Norwegian schools write it: `·` for times and `:` for divided
by.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from random import Random

from pensum.arkade.items import Item

ADD, SUBTRACT, MULTIPLY, DIVIDE = "+", "−", "·", ":"


@dataclass(frozen=True)
class Fact:
    a: int
    op: str
    b: int

    @property
    def value(self) -> int:
        if self.op == ADD:
            return self.a + self.b
        if self.op == SUBTRACT:
            return self.a - self.b
        if self.op == MULTIPLY:
            return self.a * self.b
        return self.a // self.b

    @property
    def key(self) -> str:
        return f"{self.a}{self.op}{self.b}"

    def statement(self, shown: int | None = None) -> str:
        return f"{self.a} {self.op} {self.b} = {self.value if shown is None else shown}"

    def wrong_values(self) -> set[int]:
        """Answers a pupil plausibly gives instead. Never the right one, never negative."""
        v = self.value
        out = {v - 1, v + 1, v - 2, v + 2}
        if v >= 10:
            out |= {v - 10, v + 10}
        if self.op == SUBTRACT:
            out.add(self.a + self.b)
        if self.op == MULTIPLY:
            # The neighbouring row or column of the table: 6 · 8 for 7 · 8.
            out |= {(self.a - 1) * self.b, (self.a + 1) * self.b}
            out |= {self.a * (self.b - 1), self.a * (self.b + 1)}
        if self.op == DIVIDE and self.b == 1:
            out.add(1)
        return {w for w in out if w >= 0 and w != v}


@dataclass(frozen=True)
class Family:
    """One kind of fact, the skill it is evidence for, and how to draw one."""

    name: str
    skill: str | None
    draw: Callable[[Random], Fact]


def _add_within(top: int) -> Callable[[Random], Fact]:
    def draw(rng: Random) -> Fact:
        total = rng.randint(2, top)
        a = rng.randint(1, total - 1)
        if rng.random() < 0.5:
            return Fact(a, ADD, total - a)
        return Fact(total, SUBTRACT, a)

    return draw


def _times(rows: tuple[int, ...]) -> Callable[[Random], Fact]:
    def draw(rng: Random) -> Fact:
        return Fact(rng.choice(rows), MULTIPLY, rng.randint(1, 10))

    return draw


def _divide(rng: Random) -> Fact:
    b = rng.randint(1, 10)
    return Fact(b * rng.randint(1, 10), DIVIDE, b)


WITHIN_20 = Family("within-20", "mat.add-subtract.within-20", _add_within(20))
# No skill: the year-3 adding skills are about strategy and explanation, which a
# fact drill does not show.
WITHIN_100 = Family("within-100", None, _add_within(100))
EASY_TABLES = Family("tables-2-5-10", "mat.multiply-divide.equal-groups", _times((2, 5, 10)))
TABLES = Family("tables", "mat.multiply-divide.equal-groups", _times(tuple(range(1, 11))))
DIVISION = Family("division", "mat.multiply-divide.division-strategies", _divide)


def families_for(grade: int) -> tuple[Family, ...]:
    """What a pupil in `grade` drills. Years past 4 keep drilling the tables."""
    if grade <= 2:
        return (WITHIN_20,)
    if grade == 3:
        return (WITHIN_100, EASY_TABLES)
    return (TABLES, DIVISION)


# Draws per item before giving up on finding three distinct facts. A family has
# dozens of facts, so this is never reached in practice; it bounds the loop.
MAX_DRAWS = 50


def false_statement_item(family: Family, rng: Random, candidates: int = 3) -> Item:
    """`candidates` statements from one family, exactly one of them false."""
    facts: dict[str, Fact] = {}
    for _ in range(MAX_DRAWS):
        fact = family.draw(rng)
        facts.setdefault(fact.key, fact)
        if len(facts) == candidates:
            break
    else:
        raise ValueError(f"{family.name}: too few distinct facts for {candidates} candidates")

    chosen = list(facts.values())
    false_fact = chosen[0]
    wrong = rng.choice(sorted(false_fact.wrong_values()))
    texts = [false_fact.statement(wrong)] + [fact.statement() for fact in chosen[1:]]
    order = list(range(candidates))
    rng.shuffle(order)
    return Item(
        id=f"mat:{false_fact.key}",
        rule="false_statement",
        candidates=tuple(texts[i] for i in order),
        matches=frozenset({order.index(0)}),
        answer=false_fact.statement(),
        skill=family.skill,
    )


def statement_items(grade: int, rng: Random, count: int, candidates: int = 3) -> list[Item]:
    """A round of false-statement items for `grade`, families taken in turn."""
    families = families_for(grade)
    return [
        false_statement_item(families[i % len(families)], rng, candidates) for i in range(count)
    ]
