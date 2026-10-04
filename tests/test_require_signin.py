"""Every exercise needs a signed-in pupil, where sign-in is configured.

Without a provider there is nobody to sign in as, so the exercises stay open;
the rest of the suite runs that way and covers it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_admin import ORIGIN, PUPIL, QUIZ_PATH, build, settings_with, sign_in, take_quiz

EXERCISE_PAGES = [
    "/nb/klasse/2/NOR01-08/lesing",
    "/nb/klasse/2/NOR01-08/skriving",
    "/nb/klasse/2/NOR01-08/lytting",
    "/nb/nivatest/MAT01-06",
]


@pytest.mark.parametrize("path", EXERCISE_PAGES)
def test_a_signed_out_pupil_is_sent_to_sign_in_and_back(tmp_path: Path, path: str) -> None:
    _, client = build(settings_with(tmp_path))

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/auth/login?next={path}"


def test_starting_a_quiz_signed_out_comes_back_to_the_page_with_the_form(tmp_path: Path) -> None:
    """A POST cannot be replayed after sign-in, so it returns to where it was."""
    _, client = build(settings_with(tmp_path))

    response = client.post(
        f"{QUIZ_PATH}/quiz", headers={"referer": f"{ORIGIN}{QUIZ_PATH}"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/auth/login?next={QUIZ_PATH}"


def test_a_referer_from_another_site_is_not_a_destination(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))

    response = client.post(
        f"{QUIZ_PATH}/quiz",
        headers={"referer": "https://elsewhere.example.org/nb"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/auth/login?next=/"


def test_htmx_is_told_to_navigate_rather_than_swap(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))

    response = client.get(
        "/nb/klasse/2/NOR01-08/lesing", headers={"HX-Request": "true"}, follow_redirects=False
    )

    assert response.status_code == 204
    assert response.headers["HX-Redirect"] == "/auth/login?next=/nb/klasse/2/NOR01-08/lesing"


def test_a_signed_out_pupil_records_nothing(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))

    client.post(f"{QUIZ_PATH}/quiz", follow_redirects=False)

    assert len(app.state.sessions) == 0
    assert app.state.attempts.users() == []


def test_a_signed_in_pupil_can_do_a_quiz(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)

    take_quiz(app, client)

    assert [user.sub for user in app.state.attempts.users()] == ["u-1"]


@pytest.mark.parametrize("path", ["/nb/", "/nb/klasse/2", QUIZ_PATH, "/nb/progresjon/MAT01-06"])
def test_browsing_the_curriculum_stays_open(tmp_path: Path, path: str) -> None:
    _, client = build(settings_with(tmp_path))

    assert client.get(path, follow_redirects=False).status_code == 200
