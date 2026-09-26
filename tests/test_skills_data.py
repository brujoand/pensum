"""The committed skills files, and the progression guide that shows them.

These run against `data/skills/` and the real catalogue, so they fail when an
edit or a curriculum revision breaks authored content, not only when code
changes.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from pensum.catalogue.loader import Catalogue
from pensum.i18n import curriculum_language
from pensum.skills.loader import DEFAULT_SKILLS_DIR, SkillLibrary
from pensum.skills.validate import validate
from pensum.web.app import create_app


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return Catalogue.load()


@pytest.fixture(scope="module")
def skills() -> SkillLibrary:
    return SkillLibrary.load()


@pytest.fixture(scope="module")
def client(catalogue: Catalogue) -> TestClient:
    return TestClient(create_app(catalogue))


def text_of(html: str) -> str:
    body = html[html.find("<main>") : html.find("</main>")]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()


def test_committed_skills_validate_against_the_catalogue() -> None:
    assert validate() == []


def test_every_committed_file_is_loaded(skills: SkillLibrary) -> None:
    on_disk = sorted(path.stem for path in DEFAULT_SKILLS_DIR.glob("*.yaml"))
    assert skills.subjects == on_disk


def test_matematikk_cites_every_goal(skills: SkillLibrary, catalogue: Catalogue) -> None:
    """All 101 goals, the ones kept off screen included."""
    skill_file = skills.for_subject("MAT01-06")
    assert skill_file is not None
    subject = catalogue.subject("MAT01-06")
    goals = {goal.code for goal_set in subject.goal_sets for goal in goal_set.goals}
    assert len(goals) == 101
    assert goals <= {ref for skill in skill_file.skills for ref in skill.refs}


def test_matematikk_keeps_the_design_s_off_screen_goals_off_screen(
    skills: SkillLibrary,
) -> None:
    skill_file = skills.for_subject("MAT01-06")
    off_screen = {ref for skill in skill_file.skills if not skill.assessable for ref in skill.refs}
    assert {"KM13229", "KM13262", "KM13325", "KM13259", "KM13295"} <= off_screen


def test_no_committed_skill_is_approved_without_an_instance(skills: SkillLibrary) -> None:
    """Approval is made on an instance, never by the author of the file."""
    skill_file = skills.for_subject("MAT01-06")
    assert all(skills.review_state(skill.id) == "pending" for skill in skill_file.skills)


# The progression guide -------------------------------------------------------


@pytest.mark.parametrize("locale", ["nb", "nn", "en"])
def test_the_guide_renders_in_every_locale(
    client: TestClient, skills: SkillLibrary, catalogue: Catalogue, locale: str
) -> None:
    response = client.get(f"/{locale}/progresjon/MAT01-06")
    assert response.status_code == 200
    html = response.text

    skill = skills.for_subject("MAT01-06").skill("mat.place-value.exchange-tens")
    assert str(escape(skill.i_can.get(locale))) in html
    assert str(escape(skill.teacher.get(locale))) in html

    # Udir's words, verbatim, in the page's maalform.
    goal = catalogue.subject("MAT01-06").goal_set("KV1021").goal("KM13232")
    assert str(escape(goal.text.get(curriculum_language(locale)))) in html


def test_the_guide_speaks_the_page_locale(client: TestClient) -> None:
    nb = text_of(client.get("/nb/progresjon/MAT01-06").text)
    en = text_of(client.get("/en/progresjon/MAT01-06").text)
    assert "Plassverdi og tallinja" in nb
    assert "Etter 10. trinn" in nb
    assert "Place value and the number line" in en
    assert "After year 10" in en
    assert "Plassverdi og tallinja" not in en


def test_the_guide_has_every_checkpoint_as_a_column(client: TestClient) -> None:
    html = client.get("/en/progresjon/MAT01-06").text
    thead = html[html.find("<thead>") : html.find("</thead>")]
    assert re.findall(r"After year (\d+)", thead) == [str(year) for year in range(2, 11)]


def test_the_guide_says_whose_words_are_whose(client: TestClient) -> None:
    """Pensum's reading is marked as ours before any of it is shown, and the
    goals sit inside the `.curriculum` treatment the site keeps for Udir's text."""
    html = client.get("/en/progresjon/MAT01-06").text
    assert html.find("Pensum&#39;s own reading") < html.find('class="skill"')
    assert 'class="curriculum skill-goals"' in html


def test_the_guide_labels_drafts_and_off_screen_skills(client: TestClient) -> None:
    text = text_of(client.get("/en/progresjon/MAT01-06").text)
    assert "skills are not approved on this site yet" in text
    assert "Waiting for approval" in text
    assert "Practised off screen" in text


def test_the_guide_prints(client: TestClient) -> None:
    css = client.get("/static/pensum.css").text
    print_rules = css[css.find("@media print") :]
    assert ".progression-cell-checkpoint" in print_rules


def test_a_subject_without_skills_has_no_guide(catalogue: Catalogue) -> None:
    empty = TestClient(create_app(catalogue, skills=SkillLibrary([])))
    assert empty.get("/nb/progresjon/MAT01-06").status_code == 404
    assert empty.get("/en/progresjon/MAT01-06").status_code == 404
    # And the subject page does not offer a link to a page that is not there.
    assert "/progresjon/" not in empty.get("/nb/klasse/3/MAT01-06").text


def test_an_unknown_subject_or_locale_is_not_found(client: TestClient) -> None:
    assert client.get("/nb/progresjon/XYZ01-01").status_code == 404
    assert client.get("/de/progresjon/MAT01-06").status_code == 404


def test_the_subject_page_links_to_the_guide(client: TestClient) -> None:
    html = client.get("/nb/klasse/3/MAT01-06").text
    assert 'href="/nb/progresjon/MAT01-06"' in html
