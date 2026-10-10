"""What an arithmetic drill is made of: a sum, its answer, and the mistakes made with it.

Two kinds of sum. A `Fact` is two whole numbers and an operation, and works its
own answer and mistakes out. A `Stated` sum is written out by the family that
drew it, for everything a `Fact` cannot be: a decimal, a fraction, a negative
number, a power.

Written the way Norwegian schools write it: `·` for times, `:` for divided by,
a decimal comma, and `av` for a percent of an amount. A page in English shows
a decimal point and `of` instead; the item keeps the Norwegian in its id, so
the same sum is the same item in every language.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from random import Random

ADD, SUBTRACT, MULTIPLY, DIVIDE = "+", "−", "·", ":"
# The decimal mark and the word for a share of an amount, as the generators
# write them. `shown_in` swaps them for a page that reads others.
COMMA = ","
OF = "av"


@dataclass(frozen=True)
class Notation:
    """How a page's language writes a sum: its decimal mark, and its `25 % av 80`."""

    mark: str
    of: str


NORWEGIAN = Notation(COMMA, OF)
ENGLISH = Notation(".", "of")


def num(value: Fraction | int) -> str:
    """A number as it is written: `−2,5`, `0,125`, `40`.

    Only for a number with a finite decimal form, which is every one the
    generators make.
    """
    exact = Fraction(value)
    text = format((Decimal(exact.numerator) / Decimal(exact.denominator)).normalize(), "f")
    return text.replace(".", COMMA).replace("-", SUBTRACT)


def shown_in(text: str, notation: Notation) -> str:
    """`text` as a page reads it. No sum has a comma that is not a decimal
    mark, or the word standing anywhere but between a percent and its amount."""
    if notation == NORWEGIAN:
        return text
    return text.replace(COMMA, notation.mark).replace(f" {OF} ", f" {notation.of} ")


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

    @property
    def expression(self) -> str:
        return f"{self.a} {self.op} {self.b}"

    @property
    def answer(self) -> str:
        return str(self.value)

    def statement(self, shown: int | str | None = None) -> str:
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

    def wrong_answers(self) -> list[str]:
        return [str(w) for w in sorted(self.wrong_values())]


@dataclass(frozen=True)
class Stated:
    """A sum written out: what is asked, what it equals, and what it is mistaken for.

    `value` is the answer as a number. Two sums with one value cannot share a
    memory board, however differently their answers are written: `1/2` and
    `0,5` would make a pair the board did not mean.
    """

    expression: str
    value: Fraction
    answer: str
    wrong: tuple[str, ...]

    @property
    def key(self) -> str:
        return self.expression.replace(" ", "")

    def statement(self, shown: str | None = None) -> str:
        return f"{self.expression} = {self.answer if shown is None else shown}"

    def wrong_answers(self) -> list[str]:
        """In the order written, each once, and never the answer itself."""
        return [w for w in dict.fromkeys(self.wrong) if w != self.answer]


def stated(expression: str, value: Fraction | int, wrong: list[Fraction | int | str]) -> Stated:
    """A sum whose answer is `value` written as a number. A wrong answer given
    as a number is written the same way; one given as text is kept as it is,
    for a mistake that is in the writing (`3,50` for `3,5 · 10`)."""
    return Stated(
        expression,
        Fraction(value),
        num(value),
        tuple(w if isinstance(w, str) else num(w) for w in wrong),
    )


Sum = Fact | Stated


@dataclass(frozen=True)
class Family:
    """One kind of sum, the skill it is evidence for, and how to draw one."""

    name: str
    skill: str | None
    draw: Callable[[Random], Sum]
