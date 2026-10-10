"""Sorting: the cards, and a round from start to result."""

from __future__ import annotations

import json
import re
from pathlib import Path
from random import Random

import pytest
from test_admin import PUPIL, build, settings_with, sign_in

from pensum.arkade.items import card
from pensum.arkade.rounds import Marked
from pensum.arkade.sorting import ALPHABET, CONSONANTS, NUMBERS, VOWELS, top_for
from pensum.config import Settings
from pensum.scores.xp import PER_CORRECT, PER_FINISH
from pensum.skills.loader import SkillLibrary
from pensum.web.arkade_routes import LIVES, ROUND_LENGTH, SORT_GAMES


def rng(seed: int) -> Random:
    return Random(seed)  # noqa: S311 -- reproducible rounds, not cryptography


def round_of(page: str) -> dict:
    found = re.search(r'<script type="application/json" id="sort-round">(.*?)</script>', page)
    assert found, "no round on the page"
    return json.loads(found.group(1))


def right_picks(played: dict) -> list[int]:
    return [entry["pile"] for entry in played["items"]]


# --- the cards ---------------------------------------------------------------


def test_a_card_matches_the_one_pile_it_belongs_in() -> None:
    item = card("sort:odd-even:7", "7", ("even", "odd"), "odd")

    assert item.rule == "sort"
    assert not item.is_match(0)
    assert item.is_match(1)
    assert item.answer == "7"


def test_a_card_put_right_scores_whichever_pile_it_was() -> None:
    """Unlike a balloon, where popping a false one is right and earns nothing."""
    even = card("sort:odd-even:8", "8", ("even", "odd"), "even")
    odd = card("sort:odd-even:7", "7", ("even", "odd"), "odd")

    assert Marked(even, True, 0).scores
    assert Marked(odd, True, 1).scores
    assert not Marked(odd, False, 0).scores


@pytest.mark.parametrize("grade", range(1, 11))
def test_a_number_is_in_the_pile_its_parity_says(grade: int) -> None:
    for seed in range(20):
        for item in NUMBERS.items(grade, "nb", rng(seed), 8):
            n = int(item.shown or "")
            assert 1 <= n <= top_for(grade)
            assert item.is_match(n % 2)
            assert item.spoken == item.shown
            assert item.language == "nb"


def test_year_one_sorts_numbers_to_twenty_and_year_two_to_a_hundred() -> None:
    assert top_for(1) == 20
    assert top_for(2) == 100


def test_both_sortings_end_with_year_two() -> None:
    assert NUMBERS.last_year == ALPHABET.last_year == 2


def test_a_number_is_said_in_the_language_of_the_page() -> None:
    assert {item.language for item in NUMBERS.items(2, "en", rng(1), 8)} == {"en"}


def test_a_letter_is_a_vowel_or_a_consonant_and_said_in_norwegian() -> None:
    for seed in range(20):
        for item in ALPHABET.items(1, "en", rng(seed), 8):
            letter = (item.shown or "").lower()
            assert item.is_match(0 if letter in VOWELS else 1)
            assert letter in VOWELS + CONSONANTS
            assert item.spoken == letter
            assert item.language == "nb"


def test_the_alphabet_is_the_norwegian_one_with_no_letter_in_both_piles() -> None:
    assert len(VOWELS + CONSONANTS) == len(set(VOWELS + CONSONANTS)) == 29


@pytest.mark.parametrize("sorting", [NUMBERS, ALPHABET])
def test_a_round_never_deals_a_card_twice(sorting) -> None:
    for seed in range(200):
        items = sorting.items(1, "nb", rng(seed), 8)
        assert len({item.id for item in items}) == 8


@pytest.mark.parametrize("sorting", [NUMBERS, ALPHABET])
def test_each_pile_is_asked_for_about_as_often(sorting) -> None:
    items = [item for seed in range(100) for item in sorting.items(4, "nb", rng(seed), 8)]
    first = sum(1 for item in items if item.is_match(0))

    assert 0.4 < first / len(items) < 0.6


def test_the_same_seed_deals_the_same_round() -> None:
    assert NUMBERS.items(3, "nb", rng(7), 8) == NUMBERS.items(3, "nb", rng(7), 8)


def test_every_named_skill_exists() -> None:
    library = SkillLibrary.load()
    for subject, sorting in SORT_GAMES.values():
        if sorting.skill is not None:
            assert sorting.skill in {s.id for s in library.for_subject(subject).skills}


# --- a round ------------------------------------------------------------------


@pytest.fixture
def pupil(tmp_path: Path):
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=2)
    return app, client


def test_the_hub_offers_the_sorting_games(pupil) -> None:
    _, client = pupil
    hub = client.get("/nb/arkade").text

    assert 'href="/nb/arkade/sorter/partall"' in hub
    assert 'href="/nb/arkade/sorter/vokaler"' in hub
    assert "Partall og oddetall" in hub


def test_a_round_is_eight_timed_cards_with_three_lives_and_named_piles(pupil) -> None:
    _, client = pupil

    played = round_of(client.get("/nb/arkade/sorter/partall").text)

    assert played["timed"] is True
    assert played["lives"] == LIVES
    assert played["piles"] == ["Partall", "Oddetall"]
    assert len(played["items"]) == ROUND_LENGTH
    for entry in played["items"]:
        assert int(entry["shown"]) <= 100
        assert entry["pile"] == int(entry["shown"]) % 2
        assert entry["spoken"] == entry["shown"]
        assert entry["language"] == "nb"


def test_the_piles_are_named_in_the_language_of_the_page(pupil) -> None:
    _, client = pupil

    played = round_of(client.get("/en/arkade/sorter/vokaler").text)

    assert played["piles"] == ["Vowel", "Consonant"]
    assert {entry["language"] for entry in played["items"]} == {"nb"}


def test_a_perfect_round_earns_a_point_a_card_and_evidence(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/sorter/partall").text)

    page = client.post(
        f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)}
    ).text

    assert "8 poeng" in page
    assert 'href="/nb/arkade/sorter/partall"' in page
    assert app.state.xp.total("u-1") == 8 * PER_CORRECT + PER_FINISH
    evidence = app.state.evidence.for_pupil("u-1")
    assert set(evidence) == {"mat.counting.odd-even"}
    assert len(evidence["mat.counting.odd-even"]) == 8


def test_letters_earn_xp_and_no_evidence(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/sorter/vokaler").text)

    client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)})

    assert app.state.xp.total("u-1") == 8 * PER_CORRECT + PER_FINISH
    assert app.state.evidence.for_pupil("u-1") == {}


def test_three_wrong_piles_end_the_round_on_the_server_too(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/sorter/partall").text)
    wrong = [1 - pick for pick in right_picks(played)]

    page = client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": wrong}).text

    assert "0 poeng" in page
    rows = app.state.evidence.for_pupil("u-1")["mat.counting.odd-even"]
    assert len(rows) == LIVES


def test_cards_time_took_are_not_evidence(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/sorter/partall").text)

    page = client.post(
        f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)[:3]}
    ).text

    assert "3 poeng" in page
    assert len(app.state.evidence.for_pupil("u-1")["mat.counting.odd-even"]) == 3


def test_switching_the_timer_off_untimes_the_next_round(pupil) -> None:
    _, client = pupil
    client.post("/nb/arkade/tidtaker", data={"timer": "av"})

    assert round_of(client.get("/nb/arkade/sorter/partall").text)["timed"] is False


def test_an_unknown_sorting_game_is_a_404(pupil) -> None:
    _, client = pupil

    assert client.get("/nb/arkade/sorter/geografi").status_code == 404


def test_without_sign_in_the_year_rides_in_the_address() -> None:
    _, client = build(Settings())

    played = round_of(client.get("/nb/arkade/sorter/partall?trinn=1").text)
    page = client.post(
        f"/nb/arkade/runde/{played['round']}?trinn=1", json={"picks": right_picks(played)}
    ).text

    assert 'href="/nb/arkade/sorter/partall?trinn=1"' in page
    assert all(int(entry["shown"]) <= 20 for entry in played["items"])


@pytest.mark.parametrize("year", [1, 2])
def test_the_first_two_years_are_offered_both_sortings(year: int) -> None:
    _, client = build(Settings())
    hub = client.get(f"/nb/arkade?trinn={year}").text

    assert f'href="/nb/arkade/sorter/partall?trinn={year}"' in hub
    assert f'href="/nb/arkade/sorter/vokaler?trinn={year}"' in hub


@pytest.mark.parametrize("year", range(3, 11))
def test_a_later_year_is_offered_no_sorting(year: int) -> None:
    _, client = build(Settings())
    hub = client.get(f"/nb/arkade?trinn={year}").text

    assert "/arkade/sorter/" not in hub
    assert "Sortering" not in hub


@pytest.mark.parametrize("game", ["partall", "vokaler"])
def test_a_link_kept_from_an_earlier_year_leads_back_to_the_hub(game: str) -> None:
    _, client = build(Settings())

    response = client.get(f"/nb/arkade/sorter/{game}?trinn=3", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/nb/arkade?trinn=3"


def test_with_no_year_the_pupil_is_sent_to_the_hub() -> None:
    _, client = build(Settings())

    response = client.get("/nb/arkade/sorter/partall", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/nb/arkade"
