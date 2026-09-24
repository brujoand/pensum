"""The pupil's map and the class grid, in both locales and with accounts off.

What the map must never show is asserted as carefully as what it shows: no
percentage, no other pupil, no colour in the glyphs, no glyph on a sensitive
skill. The grid is asserted to be admin-only, to show the true state, and to
leave sensitive skills out entirely.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from test_admin import ADMIN, PUPIL, build, settings_with, sign_in, take_quiz

from pensum.auth.models import User
from pensum.config import Settings
from pensum.scores.evidence import Evidence
from pensum.scores.store import Attempt

OTHER = User(sub="u-2", name="Kari", groups=("pupils",))
START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

NOT_STORED = {"nb": "lagrer ingenting om deg", "en": "stores nothing about you"}
SIGN_IN = {"nb": "Kartet ditt vokser bare", "en": "Your map only grows"}
GRID_NOT_STORED = {"nb": "ingen database", "en": "no database"}


def spots(html: str) -> str:
    """The map itself, after the legend -- which shows every glyph once."""
    return html[html.find("</details>") :]


def svgs(html: str) -> list[str]:
    return re.findall(r"<svg.*?</svg>", html, flags=re.S)


def remember(app: FastAPI, user: User, rows: list[tuple[str, str | None, bool, float]]) -> None:
    """Put a pupil on the roster and give them evidence: (skill, stage, correct, day)."""
    app.state.attempts.record(
        Attempt(
            key=f"k-{user.sub}",
            user_sub=user.sub,
            user_name=user.name,
            subject="MAT01-06",
            goal_set="KV1021",
            grade=2,
            correct=1,
            total=1,
            by_goal=(),
            finished_at=START,
        )
    )
    app.state.evidence.record(
        Evidence(
            attempt=f"k-{user.sub}-{index}",
            user_sub=user.sub,
            skill=skill,
            item=f"item-{index}",
            stage=stage,  # type: ignore[arg-type]
            correct=correct,
            hints=0,
            recorded_at=START + timedelta(days=day),
        )
        for index, (skill, stage, correct, day) in enumerate(rows)
    )


SECURE = [
    ("mat.place-value.exchange-tens", "concrete", True, 0),
    ("mat.place-value.exchange-tens", "concrete", True, 0),
    ("mat.place-value.exchange-tens", "abstract", True, 1),
    ("mat.place-value.exchange-tens", "abstract", True, 1),
]


# The map, with nothing stored -------------------------------------------------


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_default_instance_says_nothing_is_stored(locale: str) -> None:
    _, client = build(Settings())
    page = client.get(f"/{locale}/kart/MAT01-06")
    assert page.status_code == 200
    assert NOT_STORED[locale] in page.text
    assert '<svg class="growth' not in page.text


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_sign_in_without_a_database_says_nothing_is_stored(locale: str, tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path, database_path=None))
    sign_in(client, PUPIL)
    assert NOT_STORED[locale] in client.get(f"/{locale}/kart/MAT01-06").text


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_a_signed_out_pupil_is_told_the_map_needs_signing_in(locale: str, tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    page = client.get(f"/{locale}/kart/MAT01-06")
    assert page.status_code == 200
    assert SIGN_IN[locale] in page.text
    assert "/auth/login?next=" in page.text


def test_an_unknown_subject_or_one_without_skills_is_404(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    assert client.get("/nb/kart/NOPE").status_code == 404


# The map, signed in -----------------------------------------------------------


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_a_quiz_grows_the_map(locale: str, tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    take_quiz(app, client)

    page = client.get(f"/{locale}/kart/MAT01-06").text
    # Every question right, once: sprouts, and the checkpoint the quiz was on.
    assert 'class="growth growth--practising"' in spots(page)
    assert 'aria-current="page"' in page
    sprout = {"nb": "En spire", "en": "A sprout"}[locale]
    assert f'aria-label="{sprout}"' in page


def test_the_map_carries_no_numbers_about_the_pupil(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(app, PUPIL, SECURE)
    sign_in(client, PUPIL)

    page = client.get("/nb/kart/MAT01-06?trinn=2").text
    main = page[page.find("<main") : page.find("</main>")]
    text = re.sub(r"<[^>]+>", " ", main)
    # Numerals appear in skill text ("opp til 100") and the checkpoint names;
    # what must never appear is a score.
    assert "%" not in text
    assert not re.search(r"\d+\s*(av|/)\s*\d+", text)
    assert "poeng" not in text.lower()


def test_the_map_shows_nobody_else(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(app, OTHER, SECURE)
    sign_in(client, PUPIL)

    page = client.get("/nb/kart/MAT01-06?trinn=2").text
    assert "Kari" not in page
    assert "growth--secure" not in spots(page)
    assert "growth--not-started" in spots(page)


def test_the_map_never_goes_down(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(
        app,
        PUPIL,
        [*SECURE, *[("mat.place-value.exchange-tens", "abstract", False, 2)] * 3],
    )
    sign_in(client, PUPIL)
    assert "growth--secure" in spots(client.get("/nb/kart/MAT01-06?trinn=2").text)


def test_the_glyphs_carry_no_colour_and_do_not_move(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(app, PUPIL, SECURE)
    sign_in(client, PUPIL)

    page = client.get("/nb/kart/MAT01-06?trinn=2").text
    glyphs = svgs(page)
    assert glyphs
    for svg in glyphs:
        assert "fill=" not in svg
        assert "stroke=" not in svg
        assert "#" not in svg
        assert "<animate" not in svg
        assert 'role="img"' in svg
        assert 'aria-label="' in svg


def test_the_legend_explains_every_glyph(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    page = client.get("/nb/kart/MAT01-06").text
    for key in ("not-started", "exploring", "practising", "secure", "retained"):
        assert f"growth--{key}" in page


def test_a_sensitive_skill_is_on_the_map_without_a_glyph(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    skill = app.state.skills.for_subject("NAT01-05").skill("nat.body-health.puberty")

    page = client.get(f"/nb/kart/NAT01-05?trinn={skill.checkpoint}").text
    assert skill.i_can.get("nb") in page
    item = page[page.find(skill.i_can.get("nb")) - 400 : page.find(skill.i_can.get("nb"))]
    assert "<svg" not in item
    assert "Her vokser det ingen plante" in page


def test_an_unknown_checkpoint_falls_back_to_the_default(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    assert client.get("/nb/kart/MAT01-06?trinn=3").status_code == 200


def test_the_subject_page_links_to_the_map_only_when_it_can_grow(tmp_path: Path) -> None:
    _, recording = build(settings_with(tmp_path))
    _, forgetting = build(Settings())
    assert "/nb/kart/MAT01-06" in recording.get("/nb/klasse/2/MAT01-06").text
    assert "/nb/kart/MAT01-06" not in forgetting.get("/nb/klasse/2/MAT01-06").text


# The class grid ---------------------------------------------------------------


def test_the_grid_is_for_admins_only(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    assert client.get("/nb/admin/klasse/MAT01-06").status_code == 401
    sign_in(client, PUPIL)
    assert client.get("/nb/admin/klasse/MAT01-06").status_code == 403


def test_without_sign_in_there_is_no_grid() -> None:
    _, client = build(Settings())
    assert client.get("/nb/admin/klasse/MAT01-06").status_code == 404


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_without_a_database_the_grid_says_nothing_is_stored(locale: str, tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path, database_path=None))
    sign_in(client, ADMIN)
    page = client.get(f"/{locale}/admin/klasse/MAT01-06")
    assert page.status_code == 200
    assert GRID_NOT_STORED[locale] in page.text


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_grid_shows_every_pupil_and_the_true_state(locale: str, tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(
        app,
        PUPIL,
        [*SECURE, *[("mat.place-value.exchange-tens", "abstract", False, 2)] * 3],
    )
    remember(app, OTHER, [])
    sign_in(client, ADMIN)

    page = client.get(f"/{locale}/admin/klasse/MAT01-06?strand=place-value").text
    assert "Ola" in page
    assert "Kari" in page
    # Ola was secure and has slipped: the grid says practising, and says so.
    assert "class-cell--practising" in page
    slipped = {"nb": "Var sikker", "en": "Was secure"}[locale]
    assert slipped in page
    assert "class-cell--not-started" in page


def test_the_grid_marks_practising_concrete_only(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(app, PUPIL, [("mat.place-value.exchange-tens", "concrete", True, 0)])
    sign_in(client, ADMIN)

    page = client.get("/nb/admin/klasse/MAT01-06?strand=place-value").text
    assert "class-cell--concrete-only" in page
    assert "Bare med ting ennå" in page
    assert "Med ting" in page


def test_the_grid_leaves_sensitive_skills_out(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    remember(app, PUPIL, [])
    sign_in(client, ADMIN)
    saf = app.state.skills.for_subject("SAF01-05")

    page = client.get("/nb/admin/klasse/SAF01-05?strand=digital").text
    assert page.count("<tr>") > 1
    for skill in saf.skills:
        if skill.sensitive:
            assert skill.i_can.get("nb") not in page
    assert any(
        s.i_can.get("nb") in page for s in saf.skills if s.strand == "digital" and not s.sensitive
    )


def test_the_roster_links_to_the_grids(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN)
    assert "/nb/admin/klasse/MAT01-06" in client.get("/nb/admin").text
