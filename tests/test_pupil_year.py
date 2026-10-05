"""A pupil says which year they are in once, at their first exercise."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_admin import ADMIN, PUPIL, build, settings_with, sign_in

from pensum.config import Settings
from pensum.scores.profile import ProfileStore, school_year

READING = "/nb/klasse/2/NOR01-08/lesing"


def at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=UTC)


# --- the store -------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "expected"),
    [(date(2026, 7, 31), 2025), (date(2026, 8, 1), 2026), (date(2027, 1, 15), 2026)],
)
def test_the_school_year_starts_on_the_first_of_august(day: date, expected: int) -> None:
    assert school_year(day) == expected


def test_a_pupil_who_has_not_said_has_no_year(tmp_path: Path) -> None:
    assert ProfileStore(tmp_path / "p.db").grade("u-1", at(2026, 10, 5)) is None


def test_a_pupil_moves_up_a_year_after_the_summer(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "p.db")
    store.set_grade("u-1", 4, at(2026, 10, 5))

    assert store.grade("u-1", at(2027, 6, 20)) == 4
    assert store.grade("u-1", at(2027, 8, 1)) == 5
    assert store.grade("u-1", at(2029, 9, 1)) == 7


def test_a_pupil_stays_in_tenth_year_after_grunnskole(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "p.db")
    store.set_grade("u-1", 9, at(2026, 10, 5))

    assert store.grade("u-1", at(2030, 10, 5)) == 10


def test_saying_it_again_replaces_the_answer(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "p.db")
    store.set_grade("u-1", 4, at(2026, 10, 5))
    store.set_grade("u-1", 3, at(2026, 10, 6))

    assert store.grade("u-1", at(2026, 10, 7)) == 3


@pytest.mark.parametrize("grade", [0, 11])
def test_a_year_outside_grunnskole_is_refused(tmp_path: Path, grade: int) -> None:
    with pytest.raises(ValueError, match="outside grunnskole"):
        ProfileStore(tmp_path / "p.db").set_grade("u-1", grade, at(2026, 10, 5))


# --- the gate --------------------------------------------------------------


def test_a_pupil_with_no_year_is_asked_and_sent_back(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    response = client.get(READING, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/nb/trinn?next={READING}"


def test_htmx_is_told_to_navigate_to_the_question(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    response = client.get(READING, headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 204
    assert response.headers["HX-Redirect"] == f"/nb/trinn?next={READING}"


def test_the_question_is_asked_in_the_pages_language(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    page = client.get("/en/klasse/2/NOR01-08/lesing").text

    assert "Which year are you in?" in page


def test_answering_returns_to_the_exercise(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    response = client.post(
        "/nb/trinn", data={"grade": "2", "next": READING}, follow_redirects=False
    )

    assert response.headers["location"] == READING
    assert app.state.profiles.grade("u-1", datetime.now(UTC)) == 2
    assert client.get(READING, follow_redirects=False).status_code == 200


def test_answering_with_nowhere_to_return_to_opens_the_years_page(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    response = client.post("/nb/trinn", data={"grade": "6"}, follow_redirects=False)

    assert response.headers["location"] == "/nb/klasse/6"


def test_a_destination_on_another_site_is_ignored(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    response = client.post(
        "/nb/trinn",
        data={"grade": "6", "next": "//elsewhere.example.org/"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/nb/klasse/6"


def test_a_year_outside_grunnskole_is_not_saved(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=None)

    response = client.post("/nb/trinn", data={"grade": "11"}, follow_redirects=False)

    assert response.status_code == 422
    assert app.state.profiles.grade("u-1", datetime.now(UTC)) is None


def test_an_administrator_is_not_asked(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN, year=None)

    assert client.get(READING, follow_redirects=False).status_code == 200


def test_the_years_page_needs_a_signed_in_pupil(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))

    response = client.get("/nb/trinn", follow_redirects=False)

    assert response.headers["location"] == "/auth/login?next=/nb/trinn"


def test_the_years_page_does_not_exist_without_sign_in_configured() -> None:
    _, client = build(Settings())

    assert client.get("/nb/trinn", follow_redirects=False).status_code == 404


# --- where the year is used ------------------------------------------------


def test_the_years_page_shows_the_last_answer(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=7)

    page = client.get("/nb/trinn").text

    assert re.search(r'value="7"[^>]*checked', page)


def test_the_home_page_links_to_the_pupils_year(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=3)

    page = client.get("/nb/").text

    assert '<a href="/nb/klasse/3">Du går i 3. klasse.</a>' in page
    assert '<a href="/nb/trinn">Endre</a>' in page


def test_the_placement_test_starts_from_the_pupils_year(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)

    page = client.get("/nb/nivatest/MAT01-06").text

    assert '<option value="4" selected>' in page
