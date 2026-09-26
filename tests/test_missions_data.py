"""The committed missions, and the pages that print them.

These run against `data/missions/`, `data/skills/` and the real catalogue, so
they fail when an edit to either side breaks a mission, not only when code
changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape
from review_helpers import approve_app

from pensum.catalogue.loader import Catalogue
from pensum.missions.cards import CARDS
from pensum.missions.loader import MissionLibrary
from pensum.missions.validate import validate
from pensum.skills.loader import SkillLibrary
from pensum.web.app import create_app as _create_app


def create_app(*args, **kwargs):
    """An app on an instance where an administrator has approved everything.

    Review is not what this module tests, so its pages serve the committed
    content the way an instance does once somebody has done the reviewing.
    """
    app = _create_app(*args, **kwargs)
    approve_app(app)
    return app


CSS = Path(__file__).resolve().parents[1] / "src" / "pensum" / "web" / "static" / "pensum.css"

# Off-screen skills with no mission, each for a reason the design gives. The
# norsk design's last Missions row: a classroom discussion, not practised in
# Pensum. Anything else without a mission fails the coverage test below.
NOT_PRACTISED = {
    "nor.sources.self-in-digital-media",
    "nor.language.digital-media-language",
}

# The subjects whose design documents have a Missions table.
SUBJECTS = ("ENG01-06", "MAT01-06", "NAT01-05", "NOR01-08", "RLE01-04", "SAF01-05")


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return Catalogue.load()


@pytest.fixture(scope="module")
def skills() -> SkillLibrary:
    return SkillLibrary.load()


@pytest.fixture(scope="module")
def missions() -> MissionLibrary:
    return MissionLibrary.load()


@pytest.fixture(scope="module")
def client(catalogue: Catalogue) -> TestClient:
    return TestClient(create_app(catalogue))


def text_of(html: str) -> str:
    body = html[html.find("<main>") : html.find("</main>")]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def test_the_committed_missions_validate(skills: SkillLibrary) -> None:
    assert validate(skills=skills) == []


@pytest.mark.parametrize("subject", SUBJECTS)
def test_every_subject_has_missions(missions: MissionLibrary, subject: str) -> None:
    assert missions.for_subject(subject) is not None


def test_every_off_screen_skill_has_a_mission(
    skills: SkillLibrary, missions: MissionLibrary
) -> None:
    uncovered = sorted(
        skill.id
        for subject in skills.subjects
        for skill in skills.for_subject(subject).skills
        if not skill.assessable and not missions.for_skill(skill.id)
    )
    assert set(uncovered) == NOT_PRACTISED


def test_the_exempt_skills_are_still_off_screen(skills: SkillLibrary) -> None:
    """An exemption for a skill that moved on screen would hide nothing, forever."""
    by_id = {s.id: s for f in (skills.for_subject(c) for c in skills.subjects) for s in f.skills}
    for skill_id in NOT_PRACTISED:
        assert skill_id in by_id and not by_id[skill_id].assessable


def test_no_mission_is_approved_without_an_instance(missions: MissionLibrary) -> None:
    """Whether a mission is live is decided on an instance, never in its file:
    a library with no instance behind it approves nothing."""
    assert all(
        missions.review_state(m.id) == "pending"
        for subject in SUBJECTS
        for m in missions.for_subject(subject).missions
    )


def test_the_krle_philosophy_cards_are_all_used(missions: MissionLibrary) -> None:
    used = {m.card for m in missions.for_subject("RLE01-04").missions}
    assert {"question", "turn", "ladder"} <= used


# The mission page -------------------------------------------------------------


@pytest.mark.parametrize("locale", ["nb", "nn", "en"])
def test_a_mission_page_renders(
    client: TestClient, missions: MissionLibrary, skills: SkillLibrary, locale: str
) -> None:
    _, mission = missions.mission("nat.risk-card-first")
    skill = skills.for_subject("NAT01-05").skill(mission.skill)
    response = client.get(f"/{locale}/oppdrag/{mission.id}")
    assert response.status_code == 200
    html = response.text
    assert str(escape(mission.title.get(locale))) in html
    assert str(escape(skill.i_can.get(locale))) in html
    for step in mission.steps:
        assert str(escape(step.get(locale))) in html
    # The steps are checkboxes, the linked card is on the page, and there is
    # nothing to submit them to.
    assert html.count('type="checkbox"') == len(mission.steps)
    assert "mission-card--risk" in html
    assert "<form" not in html[html.find("<main>") : html.find("</main>")]
    assert "/static/missions.js" in html


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_every_mission_page_renders(
    client: TestClient, missions: MissionLibrary, locale: str
) -> None:
    for subject in SUBJECTS:
        for mission in missions.for_subject(subject).missions:
            response = client.get(f"/{locale}/oppdrag/{mission.id}")
            assert response.status_code == 200, mission.id
            # A card line that fell back to its key would show up here.
            assert "missions.card." not in text_of(response.text), mission.id


def test_a_question_card_prints_its_question(client: TestClient, missions: MissionLibrary) -> None:
    _, mission = missions.mission("krle.question-what-is-a-friend")
    html = client.get(f"/en/oppdrag/{mission.id}").text
    assert str(escape(mission.question.eng)) in html


def test_who_confirms_is_said(client: TestClient) -> None:
    assert "show your teacher" in text_of(client.get("/en/oppdrag/nat.weather-week").text)
    assert "you decide that it is done" in text_of(
        client.get("/en/oppdrag/eng.song-game-show").text
    )


def test_the_page_says_nothing_is_sent(client: TestClient) -> None:
    assert "Nothing is sent anywhere" in text_of(client.get("/en/oppdrag/nat.weather-week").text)


def test_an_unknown_mission_is_404(client: TestClient) -> None:
    assert client.get("/nb/oppdrag/nat.no-such-mission").status_code == 404


def test_an_unknown_locale_is_404(client: TestClient) -> None:
    assert client.get("/xx/oppdrag/nat.weather-week").status_code == 404


# The cards --------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(CARDS))
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_every_card_renders_on_its_own(client: TestClient, kind: str, locale: str) -> None:
    response = client.get(f"/{locale}/oppdrag/kort/{kind}")
    assert response.status_code == 200
    assert f"mission-card--{kind}" in response.text
    assert "missions.card." not in text_of(response.text)


def test_an_unknown_card_is_404(client: TestClient) -> None:
    assert client.get("/nb/oppdrag/kort/poster").status_code == 404


# The teacher's list ---------------------------------------------------------------


@pytest.mark.parametrize("locale", ["nb", "en"])
@pytest.mark.parametrize("subject", SUBJECTS)
def test_the_mission_list_renders(
    client: TestClient, missions: MissionLibrary, subject: str, locale: str
) -> None:
    response = client.get(f"/{locale}/progresjon/{subject}/oppdrag")
    assert response.status_code == 200
    for mission in missions.for_subject(subject).missions:
        assert f'href="/{locale}/oppdrag/{mission.id}"' in response.text


def test_the_list_shows_a_skill_without_a_mission(client: TestClient) -> None:
    text = text_of(client.get("/en/progresjon/NOR01-08/oppdrag").text)
    assert "No mission. This goal is left to the classroom." in text


def test_the_list_links_the_cards_its_missions_use(client: TestClient) -> None:
    html = client.get("/en/progresjon/SAF01-05/oppdrag").text
    for kind in ("interview", "solve_it", "method"):
        assert f'href="/en/oppdrag/kort/{kind}"' in html


def test_the_list_for_an_unknown_subject_is_404(client: TestClient) -> None:
    assert client.get("/nb/progresjon/XYZ01-01/oppdrag").status_code == 404


def test_the_list_for_a_subject_without_missions_is_404(
    catalogue: Catalogue, missions: MissionLibrary
) -> None:
    app = create_app(catalogue)
    app.state.missions = MissionLibrary([])
    assert TestClient(app).get("/nb/progresjon/NAT01-05/oppdrag").status_code == 404


# The progression guide ------------------------------------------------------------


def test_the_progression_guide_links_each_off_screen_skill_to_its_missions(
    client: TestClient, missions: MissionLibrary
) -> None:
    html = client.get("/nb/progresjon/NAT01-05").text
    assert 'href="/nb/progresjon/NAT01-05/oppdrag"' in html
    for mission in missions.for_subject("NAT01-05").missions:
        assert f'href="/nb/oppdrag/{mission.id}"' in html


# Print --------------------------------------------------------------------------


def test_a_mission_prints_on_one_a4_page() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"@page mission\s*\{[^}]*size:\s*A4", css)
    assert re.search(r"@media print\s*\{\s*\.mission-page\s*\{\s*page:\s*mission", css)
