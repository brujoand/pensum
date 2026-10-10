"""The sums of years 5 to 10: larger numbers, then fractions, decimals, negative
numbers, powers and the square theorems.

Each family is the arithmetic one competence goal names, and its wrong answers
are the mistakes that goal's pupils make: denominators added, a zero put on
the end of a decimal, a sign dropped, an exponent multiplied. `arithmetic`
says which year gets which.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from random import Random

from pensum.arkade.facts import ADD, DIVIDE, MULTIPLY, SUBTRACT, Family, Stated, num, stated

# --- year 5: larger whole numbers, and fractions ---------------------------------


def _tens(rng: Random) -> Stated:
    """A table fact with a ten in it: `6 · 40`, `240 : 6`."""
    a = rng.randint(2, 9)
    b = rng.randint(2, 9) * 10
    product = a * b
    if rng.random() < 0.5:
        first, second = (a, b) if rng.random() < 0.5 else (b, a)
        # The zero forgotten, or counted twice; the neighbouring row.
        wrong = [product // 10, product * 10, (a + 1) * b, (a - 1) * b]
        return stated(f"{first} {MULTIPLY} {second}", product, wrong)
    return stated(f"{product} {DIVIDE} {a}", b, [b // 10, b * 10, b + 10, b - 10])


def _fraction(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator}"


# Denominators a pupil meets as strips and pieces.
DENOMINATORS = (3, 4, 5, 6, 8, 10)


def _same_denominator(rng: Random) -> Stated:
    """Two fractions of one denominator, added or subtracted, the result under a whole.

    The answer is left as it comes out, `2/4` and not `1/2`: shortening is a
    step of its own, and the wrong answers here are about the adding.
    """
    d = rng.choice(DENOMINATORS)
    whole = rng.randint(2, d - 1)
    part = rng.randint(1, whole - 1)
    rest = whole - part
    if rng.random() < 0.5:
        # Denominators added as well: the mistake this goal is known for.
        wrong = [_fraction(whole, 2 * d), _fraction(whole + 1, d), _fraction(whole - 1, d)]
        return Stated(
            f"{_fraction(part, d)} {ADD} {_fraction(rest, d)}",
            Fraction(whole, d),
            _fraction(whole, d),
            tuple(wrong),
        )
    wrong = [_fraction(rest + 1, d), _fraction(whole + part, d)]
    if rest > 1:
        wrong.append(_fraction(rest - 1, d))
    return Stated(
        f"{_fraction(whole, d)} {SUBTRACT} {_fraction(part, d)}",
        Fraction(rest, d),
        _fraction(rest, d),
        tuple(wrong),
    )


def _forms(amount: Fraction) -> tuple[str, str, str]:
    """One amount as a fraction, a decimal and a percent."""
    return (
        _fraction(amount.numerator, amount.denominator),
        num(amount),
        f"{num(amount * 100)} %",
    )


def _glued(amount: Fraction, form: int) -> list[str]:
    """The fraction's digits read straight off as a decimal or a percent:
    `0,4` or `0,14` for 1/4, `4 %` or `14 %`."""
    if form == 0:
        return []
    out = []
    for digits in (str(amount.denominator), f"{amount.numerator}{amount.denominator}"):
        # Not where the digits happen to say the right amount: `0,10` for 1/10.
        read_as = (
            Fraction(int(digits), 10 ** len(digits)) if form == 1 else Fraction(int(digits), 100)
        )
        if read_as != amount:
            out.append(f"0,{digits}" if form == 1 else f"{digits} %")
    return out


def _same_amount(amounts: tuple[Fraction, ...]) -> Callable[[Random], Stated]:
    def draw(rng: Random) -> Stated:
        amount = rng.choice(amounts)
        asked, answered = rng.sample((0, 1, 2), 2)
        answer = _forms(amount)[answered]
        # The other amounts in the same form, nearest first, so the wrong
        # answer is one that could be believed.
        others = sorted((a for a in amounts if a != amount), key=lambda a: abs(a - amount))
        wrong = _glued(amount, answered) + [_forms(a)[answered] for a in others[:3]]
        return Stated(_forms(amount)[asked], amount, answer, tuple(wrong))

    return draw


# The amounts a 5th-grader connects in all three forms, and the wider set a
# 7th-grader converts between.
BENCHMARKS = tuple(Fraction(n, d) for n, d in ((1, 2), (1, 4), (3, 4), (1, 10), (1, 5), (1, 100)))
COMMON = BENCHMARKS + tuple(
    Fraction(n, d)
    for n, d in ((2, 5), (3, 5), (4, 5), (3, 10), (7, 10), (9, 10), (1, 8), (3, 8), (1, 20), (1, 25), (1, 50), (3, 2))
)  # fmt: skip

TENS = Family("times-tens", None, _tens)
FRACTIONS = Family("fractions-same-denominator", None, _same_denominator)
SAME_AMOUNT = Family("same-amount", "mat.fractions.same-amount", _same_amount(BENCHMARKS))


# --- year 6: decimals -------------------------------------------------------------


def _tenths(n: int) -> Fraction:
    return Fraction(n, 10)


def _decimal_sum(rng: Random) -> Stated:
    """Tenths added or subtracted: `0,7 + 0,5`, `2,3 − 0,8`."""
    a = rng.randint(1, 49)
    b = rng.randint(1, 9)
    if rng.random() < 0.5:
        total = _tenths(a + b)
        wrong: list[Fraction | int | str] = [total + _tenths(1), total - _tenths(1), total + 1]
        if a < 10 and a + b >= 10:
            # Seven tenths and five tenths read as twelve hundredths.
            wrong.insert(0, f"0,{a + b}")
        return stated(f"{num(_tenths(a))} {ADD} {num(_tenths(b))}", total, wrong)
    a += b
    left = _tenths(a - b)
    return stated(
        f"{num(_tenths(a))} {SUBTRACT} {num(_tenths(b))}",
        left,
        [_tenths(a + b), left + _tenths(1), left + 1],
    )


def _decimal_times(rng: Random) -> Stated:
    """Tenths times a whole number: `0,4 · 6`."""
    t = rng.randint(2, 9)
    n = rng.randint(2, 9)
    product = _tenths(t * n)
    # The comma left where it was, or lost.
    return stated(
        f"{num(_tenths(t))} {MULTIPLY} {n}",
        product,
        [product / 10, product * 10, _tenths(t * (n + 1))],
    )


def _tenfold(rng: Random) -> Stated:
    """A decimal times or divided by 10 or 100: `3,5 · 10`, `47 : 100`."""
    digits = rng.randint(11, 99)
    while digits % 10 == 0:
        digits = rng.randint(11, 99)
    by = rng.choice((10, 100))
    if rng.random() < 0.5:
        x = _tenths(digits)
        # A zero put on the end, as with a whole number.
        zeros = num(x) + "0" * (len(str(by)) - 1)
        return stated(f"{num(x)} {MULTIPLY} {by}", x * by, [zeros, x * by * 10, x * by / 10])
    x = Fraction(digits)
    return stated(f"{num(x)} {DIVIDE} {by}", x / by, [x / by * 10, x / by / 10, x * by])


DECIMAL_SUMS = Family("decimal-sums", "mat.fractions.decimal-arithmetic", _decimal_sum)
DECIMAL_TIMES = Family("decimal-times", "mat.fractions.decimal-arithmetic", _decimal_times)
TENFOLD = Family("tenfold", "mat.fractions.decimal-arithmetic", _tenfold)


# --- year 7: negative numbers, conversions, the order of operations ----------------


def _negative(rng: Random) -> Stated:
    """Adding and subtracting across zero: `3 − 8`, `−4 + 9`, `−2 − 5`."""
    a = rng.randint(1, 12)
    b = rng.randint(1, 12)
    while b == a:
        b = rng.randint(1, 12)
    form = rng.randrange(3)
    if form == 0:
        low, high = sorted((a, b))
        value = low - high
        # The sign dropped, or the two added.
        return stated(f"{low} {SUBTRACT} {high}", value, [-value, -(low + high), value - 1])
    if form == 1:
        value = b - a
        return stated(f"{num(-a)} {ADD} {b}", value, [-(a + b), a + b, -value])
    value = -(a + b)
    return stated(f"{num(-a)} {SUBTRACT} {b}", value, [a + b, b - a, a - b])


def _order(rng: Random) -> Stated:
    """A sum where working left to right gives the wrong answer: `2 + 3 · 4`."""
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    c = rng.randint(2, 9)
    form = rng.randrange(3)
    if form == 0:
        value = a + b * c
        return stated(f"{a} {ADD} {b} {MULTIPLY} {c}", value, [(a + b) * c, value + c, value - b])
    if form == 1:
        value = a + b
        # `8 + 12 : 4` read left to right is 5.
        left_to_right = Fraction(a + b * c, c)
        wrong: list[Fraction | int | str] = [value + 1, value - 1, a * c + b]
        if left_to_right.denominator == 1:
            wrong.insert(0, left_to_right)
        return stated(f"{a} {ADD} {b * c} {DIVIDE} {c}", value, wrong)
    value = a * (b + c)
    return stated(f"{a} {MULTIPLY} ({b} {ADD} {c})", value, [a * b + c, value + a, value - a])


NEGATIVES = Family("negative-numbers", "mat.place-value.negative-arithmetic", _negative)
CONVERT = Family("convert", "mat.fractions.convert", _same_amount(COMMON))
ORDER = Family("order-of-operations", "mat.algebra.order-of-operations", _order)


# --- year 8: powers and square roots ---------------------------------------------

SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _to_the(base: int, exponent: int) -> str:
    return f"{base}{str(exponent).translate(SUPERSCRIPT)}"


# Cubes a pupil can hold in their head.
CUBES = (2, 3, 4, 5, 10)


def _power(rng: Random) -> Stated:
    """A square, a cube or a power of ten: `7²`, `2³`, `10⁴`."""
    kind = rng.randrange(3)
    if kind == 0:
        n = rng.randint(2, 15)
        # The exponent multiplied; the neighbouring squares' products.
        return stated(_to_the(n, 2), n * n, [2 * n, n * (n + 1), n * (n - 1), n * n + 10])
    if kind == 1:
        n = rng.choice(CUBES)
        return stated(_to_the(n, 3), n**3, [3 * n, n * n, n**3 + n])
    k = rng.randint(2, 6)
    return stated(_to_the(10, k), 10**k, [10 * k, 10 ** (k - 1), 10 ** (k + 1)])


def _root(rng: Random) -> Stated:
    """The square root of a perfect square: `√81`."""
    n = rng.randint(2, 15)
    # Halved instead of rooted; the neighbouring roots.
    return stated(f"√{n * n}", n, [Fraction(n * n, 2), n + 1, n - 1])


POWERS = Family("powers", "mat.place-value.powers-and-roots", _power)
ROOTS = Family("square-roots", "mat.place-value.powers-and-roots", _root)


# --- year 10: the square theorems as a way to calculate ----------------------------


def _square_theorem(rng: Random) -> Stated:
    """A sum beside a round number, worked out with a square theorem:
    `21²` as (20 + 1)², `19 · 21` as 20² − 1²."""
    t = rng.choice((20, 30, 40, 50))
    k = rng.randint(1, 3)
    form = rng.randrange(3)
    if form == 2:
        value = t * t - k * k
        # The second square forgotten, or added.
        return stated(f"{t - k} {MULTIPLY} {t + k}", value, [t * t, t * t + k * k, value - 10])
    n = t + k if form == 0 else t - k
    value = n * n
    # The middle term forgotten: 20² + 1² for 21².
    return stated(_to_the(n, 2), value, [t * t + k * k, 2 * n, value + 10, value - 10])


SQUARE_THEOREMS = Family("square-theorems", "mat.algebra.square-theorems", _square_theorem)
