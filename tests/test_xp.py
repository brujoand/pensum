"""XP: the fixed rules, the ledger, and where a pupil sees it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from test_admin import ORIGIN, PUPIL, QUIZ_PATH, build, settings_with, sign_in, take_quiz
from test_placement_routes import answer_all, start

from pensum.config import Settings
from pensum.mastery.attribution import is_sensitive
from pensum.scores.xp import PER_CORRECT, PER_FINISH, Award, XpStore, for_run
from pensum.skills.loader import SkillLibrary

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


# The rules -------------------------------------------------------------------


def test_each_right_answer_and_finishing_earn_xp() -> None:
    assert for_run([(True, False), (True, False), (False, False)]) == 2 * PER_CORRECT + PER_FINISH


def test_a_run_with_no_right_answers_still_earns_for_finishing() -> None:
    assert for_run([(False, False), (False, False)]) == PER_FINISH


def test_a_sensitive_answer_earns_nothing() -> None:
    assert for_run([(True, True), (True, False)]) == PER_CORRECT + PER_FINISH


def test_a_run_made_only_of_sensitive_answers_earns_nothing_at_all() -> None:
    assert for_run([(True, True), (False, True)]) == 0


def test_a_goal_cited_by_a_sensitive_skill_is_sensitive() -> None:
    skill_file = SkillLibrary.load().for_subject("NAT01-05")
    assert skill_file is not None
    sensitive = next(s for s in skill_file.skills if s.sensitive)
    item = type("Item", (), {"skill": None, "goal": sensitive.refs[0]})()

    assert is_sensitive(item, sensitive.checkpoint, skill_file)
    assert not is_sensitive(item, sensitive.checkpoint, None)


# The ledger ------------------------------------------------------------------


def award(ref: str = "a", amount: int = 30, subject: str = "MAT01-06") -> Award:
    return Award(
        user_sub="u-1", source="quiz", subject=subject, ref=ref, amount=amount, recorded_at=NOW
    )


def test_the_same_award_is_kept_once(tmp_path: Path) -> None:
    store = XpStore(tmp_path / "pensum.db")
    store.record(award())
    store.record(award())

    assert store.total("u-1") == 30


def test_the_total_spans_subjects(tmp_path: Path) -> None:
    store = XpStore(tmp_path / "pensum.db")
    store.record(award("a", 30))
    store.record(award("b", 50, subject="NOR01-08"))

    assert store.total("u-1") == 80
    assert store.total("u-2") == 0


def test_a_zero_award_is_not_written(tmp_path: Path) -> None:
    store = XpStore(tmp_path / "pensum.db")
    store.record(award(amount=0))

    assert store.total("u-1") == 0


# Over HTTP -------------------------------------------------------------------


def test_a_signed_in_pupil_earns_xp_for_a_quiz_and_is_told(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)

    session_id = take_quiz(app, client)

    session = app.state.sessions.get(session_id, datetime.now(UTC))
    skill_file = app.state.skills.for_subject("MAT01-06")
    assert not any(is_sensitive(item, 2, skill_file) for item in session.items)
    expected = PER_CORRECT * len(session.items) + PER_FINISH
    assert app.state.xp.total("u-1") == expected
    page = client.get(f"/nb/quiz/{session_id}/result").text
    assert f"+{expected} XP" in page


def test_reloading_the_result_does_not_award_twice(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    session_id = take_quiz(app, client)
    once = app.state.xp.total("u-1")

    client.get(f"/nb/quiz/{session_id}/result")

    assert app.state.xp.total("u-1") == once


def test_an_abandoned_quiz_earns_nothing(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)

    client.post(f"{QUIZ_PATH}/quiz", follow_redirects=False)

    assert app.state.xp.total("u-1") == 0


def test_an_instance_without_sign_in_has_no_xp(tmp_path: Path) -> None:
    app, client = build(Settings(database_path=tmp_path / "pensum.db"))

    session_id = take_quiz(app, client)

    assert app.state.xp is None
    assert " XP" not in client.get(f"/nb/quiz/{session_id}/result").text


def test_the_map_shows_the_total(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    take_quiz(app, client)

    page = client.get("/nb/kart/MAT01-06").text

    assert f"Du har {app.state.xp.total('u-1')} XP." in page


def test_a_finished_nivatest_earns_xp(tmp_path: Path) -> None:
    app, _ = build(settings_with(tmp_path))
    client = TestClient(app, base_url=ORIGIN)
    sign_in(client, PUPIL)

    run_id = start(client)
    run = answer_all(client, run_id, correct_up_to=99)
    page = client.get(f"/nb/nivatest/run/{run_id}/result").text

    expected = PER_CORRECT * len(run.answers) + PER_FINISH
    assert app.state.xp.total("u-1") == expected
    assert f"+{expected} XP" in page
