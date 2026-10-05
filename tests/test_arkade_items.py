"""The Arkade item shape and the two generators that fill it."""

from __future__ import annotations

from random import Random

import pytest

from pensum.arkade.arithmetic import (
    DIVIDE,
    DIVISION,
    MULTIPLY,
    SUBTRACT,
    TABLES,
    WITHIN_20,
    Fact,
    false_statement_item,
    families_for,
    statement_items,
)
from pensum.arkade.items import Item
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
            rule="false_statement",
            candidates=("a", "a"),
            matches=frozenset({0}),
            answer="a",
        )


@pytest.mark.parametrize("matches", [frozenset(), frozenset({2})])
def test_an_item_must_match_one_of_its_candidates(matches: frozenset[int]) -> None:
    with pytest.raises(ValueError, match="matches"):
        Item(id="x", rule="false_statement", candidates=("a", "b"), matches=matches, answer="a")


# --- arithmetic ------------------------------------------------------------


def test_the_false_statement_is_the_one_that_matches() -> None:
    for seed in range(200):
        item = false_statement_item(TABLES, seeded(seed))
        (index,) = item.matches
        assert item.candidates[index] != item.answer
        others = [c for i, c in enumerate(item.candidates) if i != index]
        assert all(_is_true(c) for c in others)
        assert not _is_true(item.candidates[index])
        assert _is_true(item.answer)


def test_the_false_one_is_not_always_in_the_same_place() -> None:
    places = {next(iter(false_statement_item(WITHIN_20, seeded(s)).matches)) for s in range(50)}
    assert places == {0, 1, 2}


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


def test_the_youngest_add_within_twenty() -> None:
    for item in statement_items(1, seeded(3), 30):
        assert item.skill == "mat.add-subtract.within-20"
        assert _numbers_in(item.answer)[-1] <= 20


def test_from_year_four_it_is_tables_and_division() -> None:
    assert families_for(4) == (TABLES, DIVISION)
    assert families_for(10) == (TABLES, DIVISION)


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


def test_the_spoken_word_is_one_of_the_two_and_the_one_that_matches(lexicons, passages) -> None:
    items = spoken_word_items(passages, lexicons["nb"], 2, seeded(1), 8)

    assert len(items) == 8
    for item in items:
        assert len(item.candidates) == 2
        (index,) = item.matches
        assert item.candidates[index] == item.spoken == item.answer
        assert item.language == "nb"
        assert item.skill == "nor.decoding.spell-by-sound"


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
