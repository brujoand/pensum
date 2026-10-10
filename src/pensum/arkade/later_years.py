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

from pensum.arkade.facts import ADD, DIVIDE, MULTIPLY, OF, SUBTRACT, Family, Stated, num, stated

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


def _three_digits(rng: Random) -> Stated:
    """Two three-digit numbers added, or one taken from another: `346 + 228`.

    The wrong answers are a ten or a hundred off, which is a carry forgotten,
    and for a subtraction the smaller digit taken from the larger in every
    place, whichever number it stood in.
    """
    total = rng.randint(300, 999)
    a = rng.randint(101, total - 101)
    b = total - a
    if rng.random() < 0.5:
        return stated(f"{a} {ADD} {b}", total, [total - 10, total - 100, total + 10, total + 100])
    digitwise = int(
        "".join(str(abs(int(x) - int(y))) for x, y in zip(str(total), str(a), strict=True))
    )
    wrong: list[Fraction | int | str] = [b + 10, b + 100, b - 10]
    if digitwise not in (b, 0):
        wrong.insert(0, digitwise)
    return stated(f"{total} {SUBTRACT} {a}", b, wrong)


def _two_digit_times(rng: Random) -> Stated:
    """A two-digit number times a one-digit one, and the division it undoes:
    `23 · 4`, `92 : 4`."""
    tens = rng.randint(1, 9)
    ones = rng.randint(1, 9)
    n = 10 * tens + ones
    by = rng.randint(2, 9)
    product = n * by
    if rng.random() < 0.5:
        # Only the tens multiplied, or only the ones; the carry forgotten.
        wrong = [10 * tens * by + ones, 10 * tens + ones * by, product - 10, product + by]
        return stated(f"{n} {MULTIPLY} {by}", product, wrong)
    return stated(f"{product} {DIVIDE} {by}", n, [n + 1, n - 1, n + 10, n - 10])


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
# No skill, like the rest of the whole-number arithmetic of year 5: the goal is
# about strategies, and a drill shows only the answer.
THREE_DIGITS = Family("three-digit-sums", None, _three_digits)
TWO_DIGIT_TIMES = Family("two-digit-times", None, _two_digit_times)
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


def _unlike_decimals(rng: Random) -> Stated:
    """A number with two decimals and one with one, added or subtracted:
    `1,25 + 0,5`.

    The wrong answer is the two lined up on the right, as whole numbers are:
    25 and 5 hundredths.
    """
    a = rng.randint(101, 499)
    while a % 10 == 0:
        a = rng.randint(101, 499)
    b = rng.randint(1, 9)
    hundredths, tenths = Fraction(a, 100), Fraction(b, 10)
    if rng.random() < 0.5:
        value = hundredths + tenths
        return stated(
            f"{num(hundredths)} {ADD} {num(tenths)}",
            value,
            [Fraction(a + b, 100), value + Fraction(1, 10), value - Fraction(1, 10)],
        )
    value = hundredths - tenths
    return stated(
        f"{num(hundredths)} {SUBTRACT} {num(tenths)}",
        value,
        [Fraction(a - b, 100), value + Fraction(1, 10), hundredths + tenths],
    )


def _decimal_product(rng: Random) -> Stated:
    """Tenths times tenths: `0,3 · 0,2`, which is hundredths and not tenths."""
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    value = Fraction(a * b, 100)
    return stated(
        f"{num(_tenths(a))} {MULTIPLY} {num(_tenths(b))}",
        value,
        [value * 10, value * 100, _tenths(a + b)],
    )


DECIMAL_SUMS = Family("decimal-sums", "mat.fractions.decimal-arithmetic", _decimal_sum)
UNLIKE_DECIMALS = Family("unlike-decimals", "mat.fractions.decimal-arithmetic", _unlike_decimals)
DECIMAL_PRODUCTS = Family("decimal-products", "mat.fractions.decimal-arithmetic", _decimal_product)
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


def _unequal(wrong: list[str], amount: Fraction) -> tuple[str, ...]:
    """The fractions among `wrong` that are not `amount` written another way."""
    return tuple(w for w in wrong if Fraction(w) != amount)


# Pairs of denominators where one is a multiple of the other, so the sum is
# found by widening one fraction only.
RELATED = ((2, 4), (2, 6), (2, 8), (2, 10), (3, 6), (3, 9), (4, 8), (5, 10))


def _unlike_fractions(rng: Random) -> Stated:
    """Fractions of two denominators, one a multiple of the other: `1/2 + 1/4`.

    The answer is left over the larger denominator. The wrong answer adds the
    numerators and the denominators as they stand.
    """
    small, large = rng.choice(RELATED)
    times = large // small
    a = rng.randint(1, small - 1)
    b = rng.randint(1, large - 1)
    # The sum under a whole, and the two not the same amount.
    while a * times + b >= large or a * times == b:
        a = rng.randint(1, small - 1)
        b = rng.randint(1, large - 1)
    widened = a * times
    if rng.random() < 0.5:
        total = widened + b
        wrong = [_fraction(a + b, small + large), _fraction(a + b, large), _fraction(total, small)]
        return Stated(
            f"{_fraction(a, small)} {ADD} {_fraction(b, large)}",
            Fraction(total, large),
            _fraction(total, large),
            _unequal(wrong, Fraction(total, large)),
        )
    left = abs(widened - b)
    first, second = _fraction(a, small), _fraction(b, large)
    if widened < b:
        first, second = second, first
    wrong = [
        _fraction(abs(a - b) or 1, large),
        _fraction(widened + b, large),
        _fraction(left + 1, large),
    ]
    return Stated(
        f"{first} {SUBTRACT} {second}",
        Fraction(left, large),
        _fraction(left, large),
        _unequal(wrong, Fraction(left, large)),
    )


def _fraction_times(rng: Random) -> Stated:
    """A whole number times a fraction: `3 · 2/5`. The answer is left as it
    comes out, `6/5`. The wrong answer multiplies the denominator as well."""
    d = rng.choice(DENOMINATORS)
    n = rng.randint(1, d - 1)
    by = rng.randint(2, 6)
    wrong = [_fraction(n * by, d * by), _fraction(n + by, d), _fraction(n, d * by)]
    return Stated(
        f"{by} {MULTIPLY} {_fraction(n, d)}",
        Fraction(n * by, d),
        _fraction(n * by, d),
        _unequal(wrong, Fraction(n * by, d)),
    )


# Percents a pupil works out in their head, and what the amount is a multiple
# of so the answer is whole.
PERCENTS = ((10, 10), (20, 5), (25, 4), (50, 2), (75, 4))


def _percent_of(rng: Random) -> Stated:
    """A percent of an amount: `25 % av 80`."""
    percent, step = rng.choice(PERCENTS)
    amount = step * rng.randint(2, 30)
    value = amount * percent // 100
    # A tenth where a hundredth was meant, the percent given back as the
    # answer, and the percent taken away from the amount.
    wrong = [value * 10, percent, amount - percent, value + 10]
    return stated(f"{percent} % {OF} {amount}", value, [w for w in wrong if w > 0])


NEGATIVES = Family("negative-numbers", "mat.place-value.negative-arithmetic", _negative)
# No skill for these three: the year-7 skill for this goal is converting
# between the forms, which `CONVERT` is evidence for.
UNLIKE_FRACTIONS = Family("unlike-fractions", None, _unlike_fractions)
FRACTION_TIMES = Family("fraction-times", None, _fraction_times)
PERCENT_OF = Family("percent-of", None, _percent_of)
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


# Fractions in their lowest terms, to be found again from a larger one.
LOWEST = ((1, 2), (1, 3), (2, 3), (1, 4), (3, 4), (2, 5), (3, 5), (1, 6), (5, 6), (3, 8))


def _shorten(rng: Random) -> Stated:
    """A fraction to shorten as far as it goes: `12/18` is `2/3`.

    The wrong answers divide the numerator by one number and the denominator
    by another. A fraction only half shortened (`6/9`) is not offered as
    wrong: it is the same amount.
    """
    n, d = rng.choice(LOWEST)
    by = rng.choice((2, 3, 4, 5, 6))
    amount = Fraction(n, d)
    wrong = [_fraction(n, d * 2), _fraction(n * 2, d), _fraction(n, d + 1)]
    return Stated(_fraction(n * by, d * by), amount, _fraction(n, d), _unequal(wrong, amount))


def _beside_a_hundred(rng: Random) -> Stated:
    """A product worked out by splitting one factor: `6 · 98` as 6 · 100 − 6 · 2."""
    a = rng.randint(3, 9)
    k = rng.randint(1, 3)
    near = 100 - k if rng.random() < 0.5 else 100 + k
    value = a * near
    # Only the hundred multiplied, and the rest added or taken off as it was.
    forgot = a * 100 + (near - 100)
    return stated(f"{a} {MULTIPLY} {near}", value, [forgot, value + 10, value - 10, a * 100])


POWERS = Family("powers", "mat.place-value.powers-and-roots", _power)
SHORTEN = Family("shorten-fractions", "mat.multiply-divide.prime-factors", _shorten)
LAWS = Family("beside-a-hundred", "mat.multiply-divide.laws", _beside_a_hundred)
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


# --- year 9: the sum Pythagoras' theorem asks for -----------------------------------


def _squares_summed(rng: Random) -> Stated:
    """Two squares added, as the theorem has it: `6² + 8²`.

    The wrong answers square the sum instead, or add the sides and forget the
    squares.
    """
    a = rng.randint(2, 12)
    b = rng.randint(2, 12)
    value = a * a + b * b
    return stated(
        f"{_to_the(a, 2)} {ADD} {_to_the(b, 2)}",
        value,
        [(a + b) ** 2, 2 * (a + b), value + 10, value - 10],
    )


PYTHAGORAS = Family("squares-summed", "mat.shape-space.pythagoras", _squares_summed)


# --- year 10: a percent change as a growth factor ------------------------------------


def _growth_factor(rng: Random) -> Stated:
    """The factor a percent change multiplies by: `100 % + 25 %` is `1,25`."""
    percent = rng.choice((2, 3, 4, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50))
    change = Fraction(percent, 100)
    if rng.random() < 0.5:
        value = 1 + change
        # The percent alone, and 5 % read as five tenths.
        return stated(f"100 % {ADD} {percent} %", value, [change, 1 + change * 10, value * 100])
    value = 1 - change
    return stated(f"100 % {SUBTRACT} {percent} %", value, [change, value * 100, 1 + change])


# No skill: the year-10 skill beside this goal is telling linear growth from
# exponential, which a factor alone does not show.
GROWTH_FACTOR = Family("growth-factor", None, _growth_factor)
