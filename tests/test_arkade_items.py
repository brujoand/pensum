"""The Arkade item shape and the two generators that fill it."""

from __future__ import annotations

from random import Random

import pytest

from pensum.arkade.arithmetic import (
    DIVIDE,
    DIVISION,
    MULTIPLY,
    ROUND_NUMBERS,
    SUBTRACT,
    TABLES,
    WITHIN_20,
    Fact,
    families_for,
    pair_items,
    statement_item,
    statement_items,
)
from pensum.arkade.items import BALLOON_CHOICES, FLY, POP, Item
from pensum.arkade.spelling import SKILL_BY_CHECKPOINT, spoken_word_items
from pensum.items.loader import ItemBank
from pensum.listening.lexicon import Lexicon, build
from pensum.reading.library import ReadingLibrary
from pensum.skills.loader import SkillLibrary

# A 2. trinn norsk goal set with approved passages in the repository.
NOR_YEAR_2 = "KV1107"


def seeded(seed: int) -> Random:
    return Random(seed)  # noqa: S311 -- reproducible rounds, not cryptography


# --- the item --------------------------------------------------------------


def test_an_item_with_repeated_candidates_is_refused() -> None:
    with pytest.raises(ValueError, match="repeat"):
        Item(
            id="x",
            rule="statement",
            candidates=("a", "a"),
            matches=frozenset({0}),
            answer="a",
        )


@pytest.mark.parametrize("matches", [frozenset(), frozenset({2})])
def test_an_item_must_match_one_of_its_candidates(matches: frozenset[int]) -> None:
    with pytest.raises(ValueError, match="matches"):
        Item(id="x", rule="statement", candidates=("a", "b"), matches=matches, answer="a")


# --- arithmetic ------------------------------------------------------------


def test_a_balloon_flies_when_its_statement_is_true_and_pops_when_not() -> None:
    for seed in range(200):
        item = statement_item(TABLES, seeded(seed))
        assert item.candidates == BALLOON_CHOICES
        assert _is_true(item.answer)
        if _is_true(item.shown):
            assert item.matches == frozenset({FLY})
            assert item.shown == item.answer
        else:
            assert item.matches == frozenset({POP})
            assert item.shown != item.answer


def test_balloons_are_true_about_half_the_time() -> None:
    trues = sum(statement_item(WITHIN_20, seeded(s)).is_match(FLY) for s in range(200))
    assert 70 < trues < 130


def test_the_same_seed_gives_the_same_round() -> None:
    assert statement_items(4, seeded(7), 8) == statement_items(4, seeded(7), 8)


@pytest.mark.parametrize(
    ("fact", "wrong"),
    [
        (Fact(5, DIVIDE, 1), 1),
        (Fact(7, MULTIPLY, 8), 48),
        (Fact(12, SUBTRACT, 5), 17),
    ],
)
def test_a_wrong_value_is_a_mistake_a_pupil_makes(fact: Fact, wrong: int) -> None:
    assert wrong in fact.wrong_values()


def test_a_wrong_value_is_never_right_and_never_negative() -> None:
    for a in range(1, 11):
        for b in range(1, 11):
            for fact in (Fact(a + b, SUBTRACT, b), Fact(a, MULTIPLY, b), Fact(a * b, DIVIDE, b)):
                wrong = fact.wrong_values()
                assert fact.value not in wrong
                assert all(w >= 0 for w in wrong)


def test_the_youngest_add_within_ten_and_year_two_within_twenty() -> None:
    for grade, top in ((1, 10), (2, 20)):
        answers = statement_items(grade, seeded(3), 30)
        assert all(item.skill == "mat.add-subtract.within-20" for item in answers)
        assert max(max(_numbers_in(item.answer)) for item in answers) == top


def test_year_four_is_the_table_division_and_whole_tens() -> None:
    assert families_for(4) == (TABLES, DIVISION, ROUND_NUMBERS)


def test_no_later_year_drills_what_year_four_does() -> None:
    """`test_arkade_ladder` has the whole ladder; this is the one it replaced."""
    for grade in range(5, 11):
        assert not set(families_for(grade)) & {TABLES, DIVISION}


def test_every_named_skill_exists() -> None:
    library = SkillLibrary.load()
    skills = {s.id for code in ("MAT01-06", "NOR01-08") for s in library.for_subject(code).skills}
    named = {family.skill for grade in range(1, 11) for family in families_for(grade)}
    assert (named - {None}) | set(SKILL_BY_CHECKPOINT.values()) <= skills


# --- spelling --------------------------------------------------------------


@pytest.fixture(scope="module")
def lexicons() -> dict[str, Lexicon]:
    return build(ItemBank.load(), ReadingLibrary.load())


@pytest.fixture(scope="module")
def passages():
    return ReadingLibrary.load().for_goal_set(NOR_YEAR_2, unreviewed=True)


def test_a_spelling_balloon_flies_when_it_spells_the_spoken_word(lexicons, passages) -> None:
    items = spoken_word_items(passages, lexicons["nb"], 2, seeded(1), 8)

    assert len(items) == 8
    for item in items:
        assert item.candidates == BALLOON_CHOICES
        assert item.spoken == item.answer
        assert item.matches == frozenset({FLY if item.shown == item.spoken else POP})
        assert item.language == "nb"
        assert item.skill == "nor.decoding.spell-by-sound"


def test_spelling_balloons_show_both_right_and_wrong_spellings(lexicons, passages) -> None:
    items = spoken_word_items(passages, lexicons["nb"], 2, seeded(3), 8)
    assert {item.is_match(FLY) for item in items} == {True, False}


def test_a_later_year_records_no_skill(lexicons, passages) -> None:
    items = spoken_word_items(passages, lexicons["nb"], 7, seeded(1), 4)
    assert items and all(item.skill is None for item in items)


def test_no_passages_give_no_items(lexicons) -> None:
    assert spoken_word_items([], lexicons["nb"], 2, seeded(1), 8) == []


def test_different_rounds_ask_different_words(lexicons, passages) -> None:
    first = {item.spoken for item in spoken_word_items(passages, lexicons["nb"], 2, seeded(1), 8)}
    second = {item.spoken for item in spoken_word_items(passages, lexicons["nb"], 2, seeded(2), 8)}
    assert first != second


# --- helpers ---------------------------------------------------------------


def _numbers_in(statement: str) -> list[int]:
    return [int(part) for part in statement.split() if part.isdigit()]


def _is_true(statement: str) -> bool:
    a, op, b, _, shown = statement.split()
    return Fact(int(a), op, int(b)).value == int(shown)


# --- memory pairs ----------------------------------------------------------


@pytest.mark.parametrize("grade", range(1, 11))
def test_a_board_never_repeats_an_answer(grade: int) -> None:
    for seed in range(30):
        items = pair_items(grade, seeded(seed), 6)
        answers = [item.candidates[1] for item in items]
        assert len(items) == 6
        assert len(set(answers)) == 6


def test_a_pair_is_a_sum_and_its_answer() -> None:
    for item in pair_items(4, seeded(1), 6):
        expression, value = item.candidates
        assert item.rule == "pair"
        assert item.matches == frozenset({0, 1})
        assert item.answer == f"{expression} = {value}"
        assert _is_true(item.answer)
        assert item.skill is None
