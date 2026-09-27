"""Topic drills: a checkpoint's quiz narrowed to one strand of its skills."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from review_helpers import approve_app
from test_admin import PUPIL, QUIZ_PATH, build, correct_response, settings_with, sign_in

from pensum.catalogue.loader import Catalogue
from pensum.items.loader import ItemBank
from pensum.items.schema import AuthoredText, QuizItem
from pensum.quiz.topics import MIN_ITEMS, in_topic, strands_of, topics
from pensum.skills.loader import SkillLibrary
from pensum.skills.schema import SkillFile
from pensum.web.app import create_app

# 2. trinn matematikk: KM13241 is read by counting skills only, and the
# shape-space strand has exactly two questions there.
CHECKPOINT = 2
GOAL_SET = "KV1021"


def mat() -> SkillFile:
    skill_file = SkillLibrary.load().for_subject("MAT01-06")
    assert skill_file is not None
    return skill_file


def item(**overrides: object) -> QuizItem:
    fields: dict[str, object] = {
        "id": "t-01",
        "goal": "KM13241",
        "type": "numeric",
        "difficulty": 1,
        "prompt": AuthoredText(nb="Hvor mange?", en="How many?"),
        "answer": "3",
        "explanation": AuthoredText(nb="Tre.", en="Three."),
    }
    fields.update(overrides)
    return QuizItem(**fields)


def pool() -> list[QuizItem]:
    return ItemBank.load().for_goal_set(GOAL_SET, unreviewed=True)


# Deriving the topic ----------------------------------------------------------


def test_an_item_naming_its_skill_is_in_that_skills_strand() -> None:
    assert strands_of(item(skill="mat.counting.subitise"), CHECKPOINT, mat()) == {"counting"}


def test_an_item_without_a_skill_takes_the_strands_of_its_goals_skills() -> None:
    assert strands_of(item(), CHECKPOINT, mat()) == {"counting"}


def test_a_goal_read_at_another_checkpoint_gives_no_topic() -> None:
    assert strands_of(item(), 7, mat()) == set()


def test_every_committed_item_has_a_topic() -> None:
    """The chain item -> skill -> strand has no gap, so no item is undrillable."""
    library = SkillLibrary.load()
    catalogue = Catalogue.load()
    bank = ItemBank.load()
    for item_set in bank.item_sets:
        skill_file = library.for_subject(item_set.subject)
        subject = catalogue.subject(item_set.subject)
        assert skill_file is not None and subject is not None
        checkpoint = subject.goal_set(item_set.goal_set).after_year
        for one in bank.for_goal_set(item_set.goal_set, unreviewed=True):
            assert strands_of(one, checkpoint, skill_file), one.id


def test_topics_keep_the_files_order_and_drop_thin_strands() -> None:
    offered = topics(pool(), CHECKPOINT, mat())
    order = [strand.id for strand in mat().strands]
    ids = [topic.strand.id for topic in offered]
    assert ids == sorted(ids, key=order.index)
    assert "shape-space" in ids
    assert all(topic.count >= MIN_ITEMS for topic in offered)
    assert "programming" not in ids, "one question is not a drill"


def test_in_topic_keeps_only_that_strand() -> None:
    drilled = in_topic(pool(), "shape-space", CHECKPOINT, mat())
    assert len(drilled) >= MIN_ITEMS
    assert all("shape-space" in strands_of(one, CHECKPOINT, mat()) for one in drilled)


# Over HTTP -------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app(Catalogue.load(), ItemBank.load())
    approve_app(app)
    return TestClient(app)


def start(client: TestClient, topic: str) -> str:
    started = client.post(f"{QUIZ_PATH}/quiz", data={"topic": topic}, follow_redirects=False)
    assert started.status_code == 303
    return started.headers["location"].rsplit("/", 1)[-1]


def test_the_subject_page_offers_each_topic(client: TestClient) -> None:
    page = client.get(QUIZ_PATH).text
    assert 'name="topic" value="shape-space"' in page
    assert "Form og rom" in page
    assert 'value="programming"' not in page


def test_a_topic_quiz_asks_only_that_topic(client: TestClient) -> None:
    session_id = start(client, "shape-space")
    session = client.app.state.sessions.get(session_id, datetime.now(UTC))
    assert session.topic == "shape-space"
    for one in (*session.items, *session.pool):
        assert "shape-space" in strands_of(one, CHECKPOINT, mat()), one.id
    assert "Tema: Form og rom" in client.get(f"/nb/quiz/{session_id}").text


def test_an_unknown_topic_is_not_found(client: TestClient) -> None:
    started = client.post(f"{QUIZ_PATH}/quiz", data={"topic": "nope"}, follow_redirects=False)
    assert started.status_code == 404


def answer_all(client: TestClient, session_id: str) -> str:
    session = client.app.state.sessions.get(session_id, datetime.now(UTC))
    for one in list(session.items):
        client.post(
            f"/nb/quiz/{session_id}/answer",
            data={"item_id": one.id, "response": correct_response(one)},
        )
    result = client.get(f"/nb/quiz/{session_id}/result")
    assert result.status_code == 200
    return result.text


def test_a_topic_result_gives_no_verdict_on_the_trinn(client: TestClient) -> None:
    page = answer_all(client, start(client, "shape-space"))
    assert "ikke hele trinnet" in page
    assert 'class="verdict"' not in page


def test_a_topic_drill_leaves_evidence_but_no_trinntest_attempt(tmp_path: Path) -> None:
    app, signed_in = build(settings_with(tmp_path))
    sign_in(signed_in, PUPIL)
    answer_all(signed_in, start(signed_in, "shape-space"))

    evidence = app.state.evidence.for_pupil(PUPIL.sub)
    assert evidence
    assert all(skill.startswith("mat.shape-space.") for skill in evidence)
    assert app.state.attempts.attempts_for(PUPIL.sub) == []
