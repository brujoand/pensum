"""What each year drills in Arkade, checked by working every sum out again.

The generators write a sum and say what it equals. `worth` here reads the sum
back as arithmetic, knowing nothing of how it was made, so a family that
states a wrong answer as right, or offers a right one as wrong, fails.
"""

from __future__ import annotations

import re
from fractions import Fraction
from random import Random

import pytest

from pensum.arkade.arithmetic import (
    DIVISION,
    DOUBLE_HALVE,
    EASY_TABLES,
    LADDER,
    ROUND_NUMBERS,
    TABLES,
    WITHIN_10,
    WITHIN_20,
    WITHIN_100,
    families_for,
    pair_items,
    statement_items,
)
from pensum.arkade.facts import ENGLISH, NORWEGIAN, Fact, Family, Stated, num, shown_in, stated
from pensum.arkade.items import FLY
from pensum.arkade.later_years import (
    BENCHMARKS,
    COMMON,
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
from pensum.skills.loader import SkillLibrary

YEARS = range(1, 11)
EVERY_FAMILY = sorted({family for year in YEARS for family in LADDER[year]}, key=lambda f: f.name)

SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def seeded(seed: int) -> Random:
    return Random(seed)  # noqa: S311 -- reproducible rounds, not cryptography


def worth(text: str) -> Fraction:
    """A sum, or an answer, as the number it is."""
    python = text.replace(",", ".").replace("−", "-").replace("·", "*").replace(":", "/")
    # A percent of an amount is the percent times the amount.
    python = python.replace(" av ", " * ").replace(" of ", " * ")
    python = re.sub(r"√(\d+)", r"root(\1)", python)
    python = re.sub(
        r"(\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: f"{m[1]}**{m[2].translate(SUPERSCRIPTS)}", python
    )
    python = re.sub(r"(\d+(?:\.\d+)?) %", r"(\1/100)", python)
    python = re.sub(r"\d+(?:\.\d+)?", lambda m: f"F('{m[0]}')", python)
    assert re.fullmatch(r"[F'\d.()+\-*/ root]+", python), f"cannot read {text!r}"

    def root(n: Fraction) -> Fraction:
        whole = int(n**0.5)
        assert whole * whole == n, f"{n} is not a perfect square"
        return Fraction(whole)

    return Fraction(eval(python, {"__builtins__": {}}, {"F": Fraction, "root": root}))  # noqa: S307


def draws(family: Family, count: int = 300) -> list[Fact | Stated]:
    rng = seeded(11)
    return [family.draw(rng) for _ in range(count)]


# --- reading a sum back -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("7 · 8", 56),
        ("240 : 6", 40),
        ("1/5 + 2/5", Fraction(3, 5)),
        ("0,7 + 0,5", Fraction(6, 5)),
        ("12,5 %", Fraction(1, 8)),
        ("−4 + 9", 5),
        ("3 − 8", -5),
        ("2 + 3 · 4", 14),
        ("8 + 12 : 4", 11),
        ("3 · (2 + 5)", 21),
        ("7²", 49),
        ("10⁴", 10000),
        ("√81", 9),
        ("19 · 21", 399),
        ("25 % av 80", 20),
        ("100 % + 25 %", Fraction(5, 4)),
        ("1/2 + 1/4", Fraction(3, 4)),
        ("3 · 2/5", Fraction(6, 5)),
        ("6² + 8²", 100),
    ],
)
def test_the_checker_reads_a_sum_as_school_writes_it(text: str, value: Fraction) -> None:
    assert worth(text) == value


@pytest.mark.parametrize(
    ("value", "text"),
    [(Fraction(5, 2), "2,5"), (Fraction(-5, 2), "−2,5"), (Fraction(1, 8), "0,125"), (40, "40"), (10, "10")],
)  # fmt: skip
def test_a_number_is_written_with_a_comma_and_a_real_minus(value: Fraction, text: str) -> None:
    assert num(value) == text


def test_a_page_in_english_reads_a_decimal_point() -> None:
    assert shown_in("0,7 + 0,5 = 1,2", ENGLISH) == "0.7 + 0.5 = 1.2"
    assert shown_in("0,7 + 0,5 = 1,2", NORWEGIAN) == "0,7 + 0,5 = 1,2"


def test_a_page_in_english_reads_a_percent_of_an_amount() -> None:
    assert shown_in("12,5 % av 80 = 10", ENGLISH) == "12.5 % of 80 = 10"
    assert shown_in("12,5 % av 80 = 10", NORWEGIAN) == "12,5 % av 80 = 10"


def test_a_wrong_answer_is_listed_once_and_is_never_the_answer() -> None:
    assert stated("2²", 4, [4, 8, 8, "8", 2]).wrong_answers() == ["8", "2"]


# --- every family ------------------------------------------------------------------


@pytest.mark.parametrize("family", EVERY_FAMILY, ids=lambda f: f.name)
def test_what_a_family_says_a_sum_equals_is_what_it_equals(family: Family) -> None:
    for fact in draws(family):
        assert worth(fact.expression) == worth(fact.answer) == Fraction(fact.value), fact


@pytest.mark.parametrize("family", EVERY_FAMILY, ids=lambda f: f.name)
def test_no_wrong_answer_is_right_however_it_is_written(family: Family) -> None:
    for fact in draws(family):
        wrong = fact.wrong_answers()
        assert wrong, f"{fact}: a false balloon needs a wrong answer"
        assert len(set(wrong)) == len(wrong)
        for answer in wrong:
            assert worth(answer) != worth(fact.answer), f"{fact.expression} = {answer} is true"


@pytest.mark.parametrize("family", EVERY_FAMILY, ids=lambda f: f.name)
def test_a_family_has_enough_sums_for_a_round(family: Family) -> None:
    assert len({fact.key for fact in draws(family)}) >= 12


@pytest.mark.parametrize("family", EVERY_FAMILY, ids=lambda f: f.name)
def test_a_sum_fits_a_balloon(family: Family) -> None:
    for fact in draws(family):
        for answer in [fact.answer, *fact.wrong_answers()]:
            assert len(fact.statement(answer)) <= 20, fact.statement(answer)


@pytest.mark.parametrize("family", EVERY_FAMILY, ids=lambda f: f.name)
def test_a_wrong_answer_is_below_zero_only_where_the_sums_are(family: Family) -> None:
    """`2² + 2² = −2` is not a mistake anyone makes."""
    if family is NEGATIVES:
        return
    for fact in draws(family, 2000):
        for wrong in fact.wrong_answers():
            assert worth(wrong) >= 0, f"{fact.expression} = {wrong}"


def test_a_step_toward_a_goal_is_not_evidence_for_its_skill() -> None:
    """Shortening shows no prime factors, and two squares added use no theorem."""
    assert SHORTEN.skill is None
    assert PYTHAGORAS.skill is None


def test_every_named_skill_exists_and_none_is_sensitive() -> None:
    skills = {s.id: s for s in SkillLibrary.load().for_subject("MAT01-06").skills}
    for family in EVERY_FAMILY:
        if family.skill is not None:
            assert family.skill in skills, family.name
            assert not skills[family.skill].sensitive


def test_a_family_is_evidence_for_a_skill_of_a_year_it_is_drilled_in() -> None:
    """Not for a skill the pupil is not due to meet for years."""
    skills = {s.id: s for s in SkillLibrary.load().for_subject("MAT01-06").skills}
    for year in YEARS:
        for family in LADDER[year]:
            if family.skill is not None:
                assert skills[family.skill].checkpoint <= max(year, 2), (year, family.name)


# --- the mistakes a family is there to catch -----------------------------------------


def wrongs_of(family: Family, expression: str) -> set[str]:
    """Every wrong answer the family offers for a sum, whichever way it is asked."""
    found = [fact for fact in draws(family, 3000) if fact.expression == expression]
    assert found, f"{family.name} never drew {expression}"
    return {wrong for fact in found for wrong in fact.wrong_answers()}


@pytest.mark.parametrize(
    ("family", "expression", "mistake"),
    [
        # The zero forgotten.
        (TENS, "6 · 40", "24"),
        (TENS, "240 : 6", "4"),
        # Denominators added.
        (FRACTIONS, "1/5 + 2/5", "3/10"),
        # The fraction's digits read off.
        (SAME_AMOUNT, "1/4", "0,4"),
        (SAME_AMOUNT, "1/4", "4 %"),
        # Tenths read as hundredths.
        (DECIMAL_SUMS, "0,7 + 0,5", "0,12"),
        # The comma left where it was.
        (DECIMAL_TIMES, "0,4 · 6", "0,24"),
        # A zero put on the end.
        (TENFOLD, "3,5 · 10", "3,50"),
        (TENFOLD, "3,5 · 100", "3,500"),
        # The sign dropped.
        (NEGATIVES, "3 − 8", "5"),
        (NEGATIVES, "−2 − 5", "7"),
        # Worked left to right.
        (ORDER, "2 + 3 · 4", "20"),
        (ORDER, "8 + 12 : 4", "5"),
        (ORDER, "3 · (2 + 5)", "11"),
        # The exponent multiplied.
        (POWERS, "7²", "14"),
        (POWERS, "2³", "6"),
        (POWERS, "10⁴", "40"),
        # Halved, not rooted.
        (ROOTS, "√81", "40,5"),
        (ROOTS, "√64", "32"),
        # The middle term forgotten.
        (SQUARE_THEOREMS, "21²", "401"),
        (SQUARE_THEOREMS, "19 · 21", "400"),
        # Only the tens multiplied.
        (TWO_DIGIT_TIMES, "23 · 4", "83"),
        # Tenths times tenths left as tenths.
        (DECIMAL_PRODUCTS, "0,3 · 0,2", "0,6"),
        # Numerators and denominators added as they stand.
        (UNLIKE_FRACTIONS, "1/2 + 1/4", "2/6"),
        # The denominator multiplied as well.
        (FRACTION_TIMES, "3 · 2/5", "6/15"),
        # A tenth where a hundredth was meant, and the percent taken away.
        (PERCENT_OF, "25 % av 80", "200"),
        (PERCENT_OF, "25 % av 80", "55"),
        # Numerator and denominator divided by different numbers.
        (SHORTEN, "12/18", "2/6"),
        # Only the hundred multiplied.
        (LAWS, "6 · 98", "598"),
        # The sum squared.
        (PYTHAGORAS, "6² + 8²", "196"),
        # 5 % read as five tenths, and the percent alone.
        (GROWTH_FACTOR, "100 % + 5 %", "1,5"),
        (GROWTH_FACTOR, "100 % − 20 %", "0,2"),
    ],
)
def test_a_family_offers_the_mistake_its_pupils_make(
    family: Family, expression: str, mistake: str
) -> None:
    assert mistake in wrongs_of(family, expression)


def test_whole_tens_are_a_ten_or_a_hundred_off_and_never_one() -> None:
    for fact in draws(ROUND_NUMBERS):
        off = {abs(worth(wrong) - worth(fact.answer)) for wrong in fact.wrong_answers()}
        assert 10 in off
        assert 100 in off
        assert all(distance % 10 == 0 for distance in off), fact


def test_a_three_digit_subtraction_offers_each_digit_taken_from_the_larger() -> None:
    """523 − 268 worked place by place, smaller from larger, is 345."""
    seen = 0
    for fact in draws(THREE_DIGITS, 600):
        if "−" not in fact.expression:
            continue
        top, taken = fact.expression.split(" − ")
        mistake = str(
            int("".join(str(abs(int(x) - int(y))) for x, y in zip(top, taken, strict=True)))
        )
        if mistake not in (fact.answer, "0"):
            assert mistake in fact.wrong_answers(), fact
            seen += 1
    assert seen > 50


def test_decimals_of_different_lengths_offer_the_two_lined_up_on_the_right() -> None:
    """1,25 + 0,5 with the 5 under the 5 is 1,30."""
    for fact in draws(UNLIKE_DECIMALS):
        long, sign, short = fact.expression.split(" ")
        hundredths = int(long.replace(",", ""))
        tenths = int(short.replace(",", ""))
        lined_up = hundredths + tenths if sign == "+" else hundredths - tenths
        assert num(Fraction(lined_up, 100)) in fact.wrong_answers(), fact


def test_same_amount_never_offers_the_same_amount_as_wrong() -> None:
    """`0,10` is what 1/10 looks like read off, and it is also right."""
    assert "0,10" not in wrongs_of(SAME_AMOUNT, "1/10")
    assert "10 %" not in wrongs_of(SAME_AMOUNT, "1/10")


def test_the_seventh_year_converts_more_amounts_than_the_fifth() -> None:
    assert set(BENCHMARKS) < set(COMMON)
    assert {fact.value for fact in draws(SAME_AMOUNT)} == set(BENCHMARKS)
    assert Fraction(1, 8) in {fact.value for fact in draws(CONVERT, 2000)}


# --- the ladder ------------------------------------------------------------------------


def test_every_year_from_one_to_ten_has_its_own_step() -> None:
    assert sorted(LADDER) == list(YEARS)
    assert len({LADDER[year] for year in YEARS}) == 10


def test_a_year_outside_grunnskole_gets_the_nearest() -> None:
    assert families_for(0) == LADDER[1]
    assert families_for(13) == LADDER[10]


def test_the_ladder_is_the_one_the_curriculum_draws() -> None:
    assert LADDER[1] == (WITHIN_10,)
    assert LADDER[2] == (WITHIN_20,)
    assert LADDER[3] == (WITHIN_100, EASY_TABLES, DOUBLE_HALVE)
    assert LADDER[4] == (TABLES, DIVISION, ROUND_NUMBERS)
    assert LADDER[5] == (TENS, TWO_DIGIT_TIMES, THREE_DIGITS, FRACTIONS, SAME_AMOUNT)
    assert LADDER[6] == (DECIMAL_SUMS, UNLIKE_DECIMALS, DECIMAL_TIMES, DECIMAL_PRODUCTS, TENFOLD)
    assert LADDER[7] == (NEGATIVES, CONVERT, ORDER, UNLIKE_FRACTIONS, FRACTION_TIMES, PERCENT_OF)
    assert LADDER[8] == (POWERS, ROOTS, SHORTEN, LAWS)
    assert LADDER[9] == (PYTHAGORAS, POWERS, ROOTS, NEGATIVES, ORDER)
    assert LADDER[10] == (SQUARE_THEOREMS, GROWTH_FACTOR, POWERS, ROOTS)


def test_a_year_past_four_has_something_no_earlier_year_has() -> None:
    seen: set[Family] = set(LADDER[4])
    for year in range(5, 11):
        new = set(LADDER[year]) - seen
        assert new, f"year {year} only repeats earlier years"
        seen |= set(LADDER[year])


def test_whole_numbers_keep_growing_after_year_four() -> None:
    """Three-digit sums and two-digit products are year 5's, not year 4's."""
    year_4 = " ".join(fact.expression for family in LADDER[4] for fact in draws(family))
    year_5 = " ".join(fact.expression for family in LADDER[5] for fact in draws(family))

    assert not re.search(r"\d\d[1-9] [+−]", year_4)
    assert re.search(r"\d\d[1-9] [+−] \d\d\d", year_5)
    assert re.search(r"\d[1-9] · \d\b", year_5)


def test_fractions_get_harder_from_year_five_to_seven_to_eight() -> None:
    def denominators(family: Family) -> list[set[str]]:
        return [set(re.findall(r"/(\d+)", fact.expression)) for fact in draws(family)]

    assert all(len(found) == 1 for found in denominators(FRACTIONS))
    assert all(len(found) == 2 for found in denominators(UNLIKE_FRACTIONS))
    # Year 8 shortens: the answer has a smaller denominator than the fraction asked.
    for fact in draws(SHORTEN):
        assert int(fact.answer.split("/")[1]) < int(fact.expression.split("/")[1])
        assert Fraction(fact.answer).denominator == int(fact.answer.split("/")[1])


def test_a_half_shortened_fraction_is_never_offered_as_wrong() -> None:
    """`12/18 = 6/9` is true."""
    for fact in draws(SHORTEN, 2000):
        assert all(Fraction(wrong) != fact.value for wrong in fact.wrong_answers())


def biggest(year: int) -> Fraction:
    return max(abs(Fraction(fact.value)) for family in LADDER[year] for fact in draws(family))


def test_whole_numbers_grow_year_by_year() -> None:
    assert biggest(1) <= 10 < biggest(2) <= 20 < biggest(3) <= 100 < biggest(4) <= 1000


def kinds(year: int) -> set[str]:
    """What a year's sums are written with, beyond whole numbers."""
    text = " ".join(
        fact.statement() for family in LADDER[year] for fact in draws(family)
    )  # fmt: skip
    found = set()
    for kind, pattern in {
        "fraction": r"\d/\d",
        "decimal": r"\d,\d",
        "percent": r"%",
        "negative": r"(^|[ =(])−\d",
        "power": r"[²³⁴⁵⁶]",
        "root": r"√",
    }.items():
        if re.search(pattern, text):
            found.add(kind)
    return found


def test_each_kind_of_number_arrives_in_the_year_its_goal_is_set() -> None:
    for year in (1, 2, 3, 4):
        assert kinds(year) == set(), year
    assert kinds(5) == {"fraction", "decimal", "percent"}
    assert kinds(6) == {"decimal"}
    assert kinds(7) == {"fraction", "decimal", "percent", "negative"}
    assert kinds(8) == {"power", "root", "fraction"}
    assert kinds(9) == {"power", "root", "negative"}
    assert kinds(10) == {"power", "root", "percent", "decimal"}


def test_multiplication_starts_in_year_three_and_division_in_year_four() -> None:
    def written(year: int) -> str:
        return " ".join(fact.expression for family in LADDER[year] for fact in draws(family))

    assert "·" not in written(1) + written(2)
    assert "·" in written(3)
    assert " : " in written(4)
    # Halving is the one division of year 3, and it is only ever by 2.
    assert set(re.findall(r" : (\d+)", written(3))) == {"2"}


# --- rounds and boards for every year -----------------------------------------------------


@pytest.mark.parametrize("year", YEARS)
def test_a_round_of_balloons_is_true_where_it_says_so(year: int) -> None:
    for seed in range(40):
        items = statement_items(year, seeded(seed), 8)
        assert len({item.id for item in items}) == 8
        for item in items:
            left, right = (item.shown or "").rsplit(" = ", 1)
            assert (worth(left) == worth(right)) is item.is_match(FLY), item.shown
            answer_left, answer_right = item.answer.rsplit(" = ", 1)
            assert worth(answer_left) == worth(answer_right)
            assert left == answer_left


@pytest.mark.parametrize("year", YEARS)
def test_a_board_has_no_two_answers_worth_the_same(year: int) -> None:
    for seed in range(40):
        items = pair_items(year, seeded(seed), 6)
        assert len(items) == 6
        cards = [card for item in items for card in item.candidates]
        assert len(set(cards)) == 12
        assert len({worth(item.candidates[1]) for item in items}) == 6
        for item in items:
            assert worth(item.candidates[0]) == worth(item.candidates[1])


def test_english_gets_a_point_and_the_same_item() -> None:
    norwegian = statement_items(6, seeded(4), 8)
    english = statement_items(6, seeded(4), 8, ENGLISH)

    assert [item.id for item in norwegian] == [item.id for item in english]
    assert any("," in (item.shown or "") for item in norwegian)
    assert not any("," in (item.shown or "") for item in english)
    assert all(
        "," not in card for item in pair_items(6, seeded(4), 6, ENGLISH) for card in item.candidates
    )
