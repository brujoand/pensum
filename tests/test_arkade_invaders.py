"""Invaders: the targets, and a round from start to result."""

from __future__ import annotations

import json
import re
from pathlib import Path
from random import Random

import pytest
from test_admin import PUPIL, build, settings_with, sign_in

from pensum.arkade.invaders import (
    CONSONANTS,
    EVEN_SKILL,
    VOWELS,
    letter_targets,
    number_targets,
)
from pensum.arkade.items import PASS, SHOOT, TARGET_CHOICES
from pensum.scores.xp import PER_CORRECT, PER_FINISH
from pensum.skills.loader import SkillLibrary


def seeded(seed: int) -> Random:
    return Random(seed)  # noqa: S311 -- reproducible rounds, not cryptography


def describe(rule: str, token: str, matches: bool, params: dict[str, int]) -> str:
    return f"{token} {'yes' if matches else 'no'} {rule} {params.get('n', '')}".strip()


def round_of(page: str) -> dict:
    found = re.search(r'<script type="application/json" id="invaders-round">(.*?)</script>', page)
    assert found, "no round on the page"
    return json.loads(found.group(1))


def right_picks(played: dict) -> list[int]:
    return [SHOOT if entry["true"] else PASS for entry in played["items"]]


# --- the targets -----------------------------------------------------------


@pytest.mark.parametrize("grade", range(1, 11))
def test_every_number_target_is_marked_by_the_rule(grade: int) -> None:
    for seed in range(20):
        targets = number_targets(grade, seeded(seed), 12, describe)
        divisor = targets.params.get("n", 2)
        assert len(targets.items) == 12
        assert len({item.shown for item in targets.items}) == 12
        for item in targets.items:
            assert item.candidates == TARGET_CHOICES
            assert item.is_match(SHOOT) == (int(item.shown) % divisor == 0)


def test_the_youngest_shoot_even_numbers_up_to_twenty() -> None:
    targets = number_targets(1, seeded(1), 12, describe)
    assert targets.rule == "even"
    assert targets.params == {}
    assert all(int(item.shown) <= 20 for item in targets.items)
    assert all(item.skill == EVEN_SKILL for item in targets.items)


def test_older_pupils_divide_and_record_no_skill() -> None:
    targets = number_targets(5, seeded(1), 12, describe)
    assert targets.rule == "divisible"
    assert targets.params["n"] in (3, 4, 5, 6, 9)
    assert all(item.skill is None for item in targets.items)


def test_about_half_the_targets_match() -> None:
    matches = sum(
        item.is_match(SHOOT)
        for seed in range(30)
        for item in number_targets(4, seeded(seed), 12, describe).items
    )
    assert 120 < matches < 240


@pytest.mark.parametrize("language", ["nb", "en"])
def test_letters_are_consonants_or_vowels(language: str) -> None:
    for seed in range(20):
        targets = letter_targets(language, seeded(seed), 12, describe)
        assert targets.rule in ("consonants", "vowels")
        for item in targets.items:
            consonant = item.shown in CONSONANTS[language]
            assert consonant or item.shown in VOWELS[language]
            assert item.is_match(SHOOT) == (consonant == (targets.rule == "consonants"))


def test_english_leaves_out_y() -> None:
    assert "Y" not in VOWELS["en"] + CONSONANTS["en"]


def test_the_answer_says_what_the_target_was() -> None:
    targets = number_targets(5, seeded(2), 12, describe)
    item = targets.items[0]
    word = "yes" if item.is_match(SHOOT) else "no"
    assert item.answer == f"{item.shown} {word} divisible {targets.params['n']}"


def test_the_even_skill_exists() -> None:
    skills = {s.id for s in SkillLibrary.load().for_subject("MAT01-06").skills}
    assert EVEN_SKILL in skills


# --- the pages -------------------------------------------------------------


@pytest.fixture
def pupil(tmp_path: Path):
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)
    return app, client


def test_the_hub_offers_both_invader_games(pupil) -> None:
    _, client = pupil
    page = client.get("/nb/arkade").text
    assert 'href="/nb/arkade/romskip/tall"' in page
    assert 'href="/nb/arkade/romskip/bokstaver"' in page


def test_a_round_is_twelve_targets_and_a_rule(pupil) -> None:
    _, client = pupil

    played = round_of(client.get("/nb/arkade/romskip/tall").text)

    assert played["lives"] == 3
    assert played["timed"] is True
    assert len(played["items"]) == 12
    assert played["rule"].startswith("Skyt tallene som kan deles på ")
    assert all(entry["answer"].startswith(entry["shown"] + " kan") for entry in played["items"])


def test_letters_are_in_the_pages_language(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=2)

    played = round_of(client.get("/en/arkade/romskip/bokstaver").text)

    assert played["rule"] in ("Shoot the consonants.", "Shoot the vowels.")
    assert all(entry["shown"] != "Y" for entry in played["items"])


def test_a_perfect_round_scores_the_matches_shot(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/romskip/tall").text)
    shot = sum(1 for entry in played["items"] if entry["true"])

    page = client.post(
        f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)}
    ).text

    assert f"{shot} poeng" in page
    assert app.state.xp.total("u-1") == shot * PER_CORRECT + PER_FINISH
    assert 'href="/nb/arkade/romskip/tall"' in page


def test_even_numbers_are_evidence(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=1)
    played = round_of(client.get("/nb/arkade/romskip/tall").text)

    client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)})

    rows = [row for rows in app.state.evidence.for_pupil("u-1").values() for row in rows]
    assert len(rows) == 12
    assert {row.skill for row in rows} == {EVEN_SKILL}


def test_three_wrong_calls_end_the_round(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/romskip/tall").text)
    wrong = [PASS if entry["true"] else SHOOT for entry in played["items"]]

    page = client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": wrong}).text

    assert "0 poeng" in page
    assert app.state.xp.total("u-1") == PER_FINISH


def test_an_unknown_invader_game_is_a_404(pupil) -> None:
    _, client = pupil
    assert client.get("/nb/arkade/romskip/land").status_code == 404
