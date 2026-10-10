"""Arithmetic statements, true and false, generated for a pupil's year.

Nothing here is authored. A sum's false version is a mistake a pupil plausibly
makes with it: one off, ten off, the neighbouring row of the times table, or
`5 : 1 = 1`. A false statement that nobody would believe is a free point, not
a drill.

`LADDER` says what each year drills, and which competence goal says so. The
sums of years 1 to 4 are here; `later_years` has the rest.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from random import Random

from pensum.arkade.facts import (
    ADD,
    DIVIDE,
    MULTIPLY,
    NORWEGIAN,
    SUBTRACT,
    Fact,
    Family,
    Notation,
    Stated,
    Sum,
    shown_in,
    stated,
)
from pensum.arkade.items import Item, balloon
from pensum.arkade.later_years import (
    CONVERT,
    DECIMAL_PRODUCTS,
    DECIMAL_SUMS,
    DECIMAL_TIMES,
    FRACTION_TIMES,
    FRACTIONS,
    GROWTH_FACTOR,
    LAWS,
    NEGATIVES,
    ORDER,
    PERCENT_OF,
    POWERS,
    PYTHAGORAS,
    ROOTS,
    SAME_AMOUNT,
    SHORTEN,
    SQUARE_THEOREMS,
    TENFOLD,
    TENS,
    THREE_DIGITS,
    TWO_DIGIT_TIMES,
    UNLIKE_DECIMALS,
    UNLIKE_FRACTIONS,
)


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


def _double_or_halve(rng: Random) -> Fact:
    """A number to 50 doubled, or an even number to 100 halved: `34 + 34`, `68 : 2`."""
    n = rng.randint(6, 50)
    if rng.random() < 0.5:
        return Fact(n, ADD, n)
    return Fact(2 * n, DIVIDE, 2)


def _round_numbers(rng: Random) -> Stated:
    """Whole tens added or subtracted within 1000: `340 + 250`, `600 − 180`.

    One off is not a mistake anyone makes with whole tens, so the wrong
    answers are a ten or a hundred off.
    """
    total = rng.randint(11, 100) * 10
    a = rng.randint(1, total // 10 - 1) * 10
    if rng.random() < 0.5:
        value = total
        expression = f"{a} {ADD} {total - a}"
        wrong: list[Fraction | int | str] = [value + 10, value - 10, value + 100, value - 100]
    else:
        value = total - a
        expression = f"{total} {SUBTRACT} {a}"
        wrong = [value + 10, value - 10, value + 100, total + a]
    return stated(expression, value, [w for w in wrong if isinstance(w, int) and w > 0])


WITHIN_10 = Family("within-10", "mat.add-subtract.within-20", _add_within(10))
WITHIN_20 = Family("within-20", "mat.add-subtract.within-20", _add_within(20))
# No skill: the year-3 adding skills are about strategy and explanation, which a
# fact drill does not show.
WITHIN_100 = Family("within-100", None, _add_within(100))
EASY_TABLES = Family("tables-2-5-10", "mat.multiply-divide.equal-groups", _times((2, 5, 10)))
DOUBLE_HALVE = Family("double-halve", "mat.multiply-divide.double-halve", _double_or_halve)
TABLES = Family("tables", "mat.multiply-divide.equal-groups", _times(tuple(range(1, 11))))
DIVISION = Family("division", "mat.multiply-divide.division-strategies", _divide)
# No skill: the year-4 goal is about how the four operations relate.
ROUND_NUMBERS = Family("round-numbers", None, _round_numbers)

# What each year drills, and the competence goals of LK20 (MAT01-06) that say
# so. A year gets the sums its own goals name: smaller numbers first, then
# larger ones, then fractions and decimals, then negative numbers and powers.
#
# A goal names an operation and a kind of number. It names no range: "to 10",
# "to 100" and "the 2, 5 and 10 tables" are this ladder's reading of how far a
# year gets, and `docs/design/arkade.md` says which rows are that.
#
#  1  KM13234  adding and subtracting, to 10
#  2  KM13234  adding and subtracting, to 20
#  3  KM13243  adding and subtracting, to 100
#     KM13245  multiplication by counting and grouping: the 2, 5 and 10 tables
#     KM13254  doubling and halving
#  4  KM13257  division, and the whole table it is read backwards from
#     KM13258  written and mental arithmetic with all four operations: whole
#              tens added and subtracted, to 1000
#  5  KM13268  arithmetic with positive numbers: table facts with a ten in
#              them, two digits times one, three-digit sums
#     KM13268  and with fractions: one denominator, added and subtracted
#     KM13265  a fraction, a decimal and a percent that are the same amount
#  6  KM13276  arithmetic with decimals: sums, times a whole number, tenths
#              times tenths, by 10 and 100
#     KM13275  numbers with different numbers of decimals, added and subtracted
#  7  KM13292  negative numbers
#     KM13286  converting between fraction, decimal and percent
#     KM13287  the order of operations
#     KM13288  arithmetic with fractions and percent: two denominators, a whole
#              number times a fraction, a percent of an amount
#  8  KM13297  powers and square roots
#     KM13298  factorising to shorten a fraction
#     KM13303  the distributive law as a way to calculate: a product beside 100
#  9  KM13317  the sum of two squares, which Pythagoras' theorem asks for.
#              No other goal of year 9 is arithmetic with numbers alone, so the
#              year also keeps powers, roots, negative numbers and the order
#              of operations
# 10  KM13318  the square theorems as a way to calculate
#     KM13322  a percent change as a growth factor
LADDER: dict[int, tuple[Family, ...]] = {
    1: (WITHIN_10,),
    2: (WITHIN_20,),
    3: (WITHIN_100, EASY_TABLES, DOUBLE_HALVE),
    4: (TABLES, DIVISION, ROUND_NUMBERS),
    5: (TENS, TWO_DIGIT_TIMES, THREE_DIGITS, FRACTIONS, SAME_AMOUNT),
    6: (DECIMAL_SUMS, UNLIKE_DECIMALS, DECIMAL_TIMES, DECIMAL_PRODUCTS, TENFOLD),
    7: (NEGATIVES, CONVERT, ORDER, UNLIKE_FRACTIONS, FRACTION_TIMES, PERCENT_OF),
    8: (POWERS, ROOTS, SHORTEN, LAWS),
    9: (PYTHAGORAS, POWERS, ROOTS, NEGATIVES, ORDER),
    10: (SQUARE_THEOREMS, GROWTH_FACTOR, POWERS, ROOTS),
}


def families_for(grade: int) -> tuple[Family, ...]:
    """What a pupil in `grade` drills. A year outside 1 to 10 gets the nearest."""
    return LADDER[min(max(grade, min(LADDER)), max(LADDER))]


# Draws before giving up on a board of distinct answers. A family has dozens of
# facts, so this is never reached in practice; it bounds the loop.
MAX_DRAWS = 50


def statement_item(
    family: Family,
    rng: Random,
    avoid: frozenset[str] = frozenset(),
    notation: Notation = NORWEGIAN,
) -> Item:
    """One balloon: a sum from `family`, shown true or, half the time, with a wrong answer.

    A sum whose key is in `avoid` is drawn again, so a round never asks the
    same sum twice: the second answer would also be dropped from the evidence,
    which is keyed on the round and the item. `notation` is how the page's
    language writes a sum.
    """
    for _ in range(MAX_DRAWS):
        fact = family.draw(rng)
        if fact.key not in avoid:
            break
    true = rng.random() < 0.5
    shown = fact.statement() if true else fact.statement(rng.choice(fact.wrong_answers()))
    return balloon(
        f"mat:{fact.key}",
        "statement",
        shown_in(shown, notation),
        true=true,
        answer=shown_in(fact.statement(), notation),
        skill=family.skill,
    )


def statement_items(
    grade: int, rng: Random, count: int, notation: Notation = NORWEGIAN
) -> list[Item]:
    """A round of balloons for `grade`, families taken in turn."""
    families = families_for(grade)
    items: list[Item] = []
    for i in range(count):
        seen = frozenset(item.id.removeprefix("mat:") for item in items)
        items.append(statement_item(families[i % len(families)], rng, seen, notation))
    return items


def pair_items(grade: int, rng: Random, count: int, notation: Notation = NORWEGIAN) -> list[Item]:
    """`count` sums for a memory board: each a card with the sum and a card with its answer.

    No two answers are the same number. `3 · 8` and `4 · 6` on one board would
    make a pupil who matched `3 · 8` with the 24 meant for `4 · 6` wrong for
    knowing it, so a sum whose answer is already on the board is drawn again.
    The same number written two ways is the same answer: `1/2` and `0,5`.

    No skill: a wrong turn in memory is forgetting where a card lay, not
    getting the sum wrong, so a board is no evidence either way.
    """
    families = families_for(grade)
    facts: list[Sum] = []
    values: set[Fraction] = set()
    for draw in range(MAX_DRAWS * count):
        fact = families[draw % len(families)].draw(rng)
        value = Fraction(fact.value)
        if value in values:
            continue
        facts.append(fact)
        values.add(value)
        if len(facts) == count:
            break
    else:
        raise ValueError(f"year {grade}: too few distinct answers for {count} pairs")

    return [
        Item(
            id=f"pair:{fact.key}",
            rule="pair",
            candidates=(shown_in(fact.expression, notation), shown_in(fact.answer, notation)),
            matches=frozenset({0, 1}),
            answer=shown_in(fact.statement(), notation),
        )
        for fact in facts
    ]
