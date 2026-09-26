"""Evidence: what is stored, when, under which skill -- and when nothing is.

The privacy promises are asserted as hard as the mechanics: the table has the
columns the README lists and no others, an anonymous or abandoned quiz writes
nothing, and an instance without a database has no evidence store at all.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from test_admin import (
    PUPIL,
    QUIZ_PATH,
    build,
    correct_response,
    settings_with,
    sign_in,
    take_quiz,
)

from pensum.catalogue.loader import Catalogue
from pensum.config import Settings
from pensum.items.schema import QuizItem
from pensum.items.validate import validate as validate_items
from pensum.mastery.attribution import evidence_for, skills_for
from pensum.mastery.rules import State, assess, is_secure
from pensum.scores.evidence import Evidence, EvidenceStore
from pensum.skills.loader import DEFAULT_SKILLS_DIR, SkillLibrary
from pensum.skills.schema import SkillFile
from pensum.skills.validate import validate as validate_skills

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def row(**overrides: object) -> Evidence:
    defaults: dict[str, object] = {
        "attempt": "k1",
        "user_sub": "u-1",
        "skill": "mat.place-value.exchange-tens",
        "item": "KM13232-04",
        "stage": "concrete",
        "correct": True,
        "hints": 0,
        "recorded_at": NOW,
    }
    return Evidence(**(defaults | overrides))  # type: ignore[arg-type]


def item(**overrides: object) -> QuizItem:
    defaults: dict[str, object] = {
        "id": "t-1",
        "goal": "KM13232",
        "type": "numeric",
        "difficulty": 1,
        "prompt": {"nb": "Hvor mye?", "en": "How much?"},
        "explanation": {"nb": "Så mye.", "en": "That much."},
        "answer": 34,
    }
    return QuizItem.model_validate(defaults | overrides)


def mat() -> SkillFile:
    skill_file = SkillLibrary.load().for_subject("MAT01-06")
    assert skill_file is not None
    return skill_file


# The store ----------------------------------------------------------------------


def test_the_table_holds_exactly_the_documented_columns(tmp_path: Path) -> None:
    """No response, no timing. A new column here is a README change first."""
    EvidenceStore(tmp_path / "pensum.db")
    with sqlite3.connect(tmp_path / "pensum.db") as connection:
        columns = [r[1] for r in connection.execute("PRAGMA table_info(evidence)")]
    assert columns == [
        "attempt",
        "user_sub",
        "skill",
        "item",
        "stage",
        "correct",
        "hints",
        "recorded_at",
    ]


def test_recording_is_idempotent(tmp_path: Path) -> None:
    """A reloaded result page must not turn one answer into two."""
    store = EvidenceStore(tmp_path / "pensum.db")
    store.record([row()])
    store.record([row()])
    assert len(store.for_pupil("u-1")["mat.place-value.exchange-tens"]) == 1


def test_rows_come_back_by_skill_oldest_first(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "pensum.db")
    store.record(
        [
            row(attempt="k2", recorded_at=NOW + timedelta(days=1), correct=False),
            row(attempt="k1"),
            row(attempt="k1", skill="mat.place-value.tens-and-ones", stage=None),
            row(attempt="k3", user_sub="u-2"),
        ]
    )
    mine = store.for_pupil("u-1")
    assert [r.attempt for r in mine["mat.place-value.exchange-tens"]] == ["k1", "k2"]
    assert mine["mat.place-value.tens-and-ones"][0].stage is None
    assert mine["mat.place-value.exchange-tens"][0].recorded_at == NOW

    everyone = store.for_skills(["mat.place-value.exchange-tens"])
    assert set(everyone) == {"u-1", "u-2"}
    assert "mat.place-value.tens-and-ones" not in everyone["u-1"]
    assert store.for_skills([]) == {}


def test_evidence_shares_the_attempts_file(tmp_path: Path) -> None:
    """One file for an adult to copy, inspect or delete."""
    app, _ = build(settings_with(tmp_path))
    assert app.state.evidence.path == app.state.attempts.path


# Attribution --------------------------------------------------------------------


def test_a_named_skill_is_the_only_one_credited() -> None:
    [skill] = skills_for(item(skill="mat.place-value.exchange-tens"), 2, mat())
    assert skill.id == "mat.place-value.exchange-tens"


def test_without_a_name_every_assessable_skill_citing_the_goal_is_credited() -> None:
    """The coarse fallback: KM13232 is two skills, and both are credited."""
    ids = {s.id for s in skills_for(item(), 2, mat())}
    assert ids == {"mat.place-value.tens-and-ones", "mat.place-value.exchange-tens"}


def test_the_fallback_respects_the_checkpoint() -> None:
    assert skills_for(item(), 4, mat()) == ()


def test_a_skill_practised_off_screen_is_never_credited() -> None:
    skill_file = mat()
    off_screen = next(s for s in skill_file.skills if not s.assessable)
    credited = skills_for(item(goal=off_screen.refs[0]), off_screen.checkpoint, skill_file)
    assert off_screen not in credited


def test_a_sensitive_skill_is_never_credited() -> None:
    nat = SkillLibrary.load().for_subject("NAT01-05")
    assert nat is not None
    puberty = nat.skill("nat.body-health.puberty")
    assert puberty is not None and puberty.sensitive
    by_goal = skills_for(item(goal=puberty.refs[0]), puberty.checkpoint, nat)
    by_name = skills_for(item(goal=puberty.refs[0], skill=puberty.id), puberty.checkpoint, nat)
    assert puberty not in by_goal
    assert by_name == ()


def test_evidence_for_writes_one_row_per_answer_and_skill() -> None:
    rows = evidence_for(
        [(item(), True, 0), (item(id="t-2", skill="mat.place-value.exchange-tens"), False, 0)],
        attempt="k",
        user_sub="u-1",
        checkpoint=2,
        skill_file=mat(),
        at=NOW,
    )
    assert sorted((r.item, r.skill, r.correct) for r in rows) == [
        ("t-1", "mat.place-value.exchange-tens", True),
        ("t-1", "mat.place-value.tens-and-ones", True),
        ("t-2", "mat.place-value.exchange-tens", False),
    ]
    assert all(r.hints == 0 and r.recorded_at == NOW for r in rows)


def test_evidence_for_carries_the_hints_used_onto_every_row_of_that_answer() -> None:
    rows = evidence_for(
        [(item(), True, 2), (item(id="t-2", skill="mat.place-value.exchange-tens"), True, 0)],
        attempt="k",
        user_sub="u-1",
        checkpoint=2,
        skill_file=mat(),
        at=NOW,
    )
    assert sorted((r.item, r.skill, r.hints) for r in rows) == [
        ("t-1", "mat.place-value.exchange-tens", 2),
        ("t-1", "mat.place-value.tens-and-ones", 2),
        ("t-2", "mat.place-value.exchange-tens", 0),
    ]


def test_a_hinted_correct_answer_does_not_by_itself_count_towards_secure() -> None:
    """Three clean answers and one hinted one: one short of secure, not secure."""
    exchange = mat().skill("mat.place-value.exchange-tens")
    assert exchange is not None

    def answered(day: int, stage: str, hints: int) -> list[Evidence]:
        return evidence_for(
            [(item(id=f"t-{day}-{hints}", skill=exchange.id, stage=stage), True, hints)],
            attempt=f"k{day}",
            user_sub="u-1",
            checkpoint=exchange.checkpoint,
            skill_file=mat(),
            at=NOW + timedelta(days=day),
        )

    first, last = exchange.stages[0], exchange.stages[-1]
    clean = [*answered(0, first, 0), *answered(0, first, 0), *answered(1, last, 0)]
    unhinted = [*clean, *answered(1, last, 0)]
    hinted = [*clean, *answered(1, last, 1)]

    assert is_secure(unhinted, exchange), "the same run without the hint is secure"
    assert not is_secure(hinted, exchange)
    assert assess(hinted, exchange).current == State.PRACTISING


# Recording through the quiz -----------------------------------------------------


def test_a_signed_in_pupil_who_finishes_leaves_evidence(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    take_quiz(app, client)

    evidence = app.state.evidence.for_pupil(PUPIL.sub)
    assert evidence
    assert all(skill.startswith("mat.") for skill in evidence)
    [attempt] = app.state.attempts.attempts_for(PUPIL.sub)
    assert {r.attempt for rows in evidence.values() for r in rows} == {attempt.key}


def test_hints_taken_in_a_quiz_are_recorded_and_never_lower_the_score(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    started = client.post(f"{QUIZ_PATH}/quiz", follow_redirects=False)
    session_id = started.headers["location"].rsplit("/", 1)[-1]
    session = app.state.sessions.get(session_id, datetime.now(UTC))
    assert session is not None

    first = session.items[0]
    client.post(f"/nb/quiz/{session_id}/help", data={"item_id": first.id})
    assert session.hints_used(first.id) == 1
    for quiz_item in list(session.items):
        client.post(
            f"/nb/quiz/{session_id}/answer",
            data={"item_id": quiz_item.id, "response": correct_response(quiz_item)},
        )
    assert client.get(f"/nb/quiz/{session_id}/result").status_code == 200

    rows = [r for rows in app.state.evidence.for_pupil(PUPIL.sub).values() for r in rows]
    assert rows
    assert {r.hints for r in rows if r.item == first.id} == {1}
    assert {r.hints for r in rows if r.item != first.id} == {0}
    [attempt] = app.state.attempts.attempts_for(PUPIL.sub)
    assert attempt.correct == attempt.total, "a hinted right answer is still right"


def test_a_quiz_without_hints_records_zero_hints(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    take_quiz(app, client)
    rows = [r for rows in app.state.evidence.for_pupil(PUPIL.sub).values() for r in rows]
    assert rows
    assert {r.hints for r in rows} == {0}


def test_reloading_the_result_page_adds_no_evidence(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    session_id = take_quiz(app, client)
    before = sum(len(v) for v in app.state.evidence.for_pupil(PUPIL.sub).values())
    client.get(f"/nb/quiz/{session_id}/result")
    after = sum(len(v) for v in app.state.evidence.for_pupil(PUPIL.sub).values())
    assert before == after > 0


def test_an_anonymous_pupil_leaves_no_evidence(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    take_quiz(app, client)
    assert app.state.evidence.for_skills([s.id for s in mat().skills]) == {}


def test_an_abandoned_quiz_leaves_no_evidence(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    started = client.post(f"{QUIZ_PATH}/quiz", follow_redirects=False)
    session_id = started.headers["location"].rsplit("/", 1)[-1]
    session = app.state.sessions.get(session_id, datetime.now(UTC))
    client.post(
        f"/nb/quiz/{session_id}/answer",
        data={"item_id": session.items[0].id, "response": ""},
    )
    assert app.state.evidence.for_pupil(PUPIL.sub) == {}


def test_with_no_database_path_evidence_goes_to_the_default_database(
    tmp_path: Path, default_database_in_tmp: Path
) -> None:
    """There is always a database: accounts on and no path configured means the
    default file, and nothing is written anywhere else."""
    app, client = build(settings_with(tmp_path, database_path=None))
    sign_in(client, PUPIL)
    take_quiz(app, client)
    assert app.state.evidence is not None
    assert app.state.evidence.for_pupil(PUPIL.sub)
    assert default_database_in_tmp.exists()
    assert [p.name for p in tmp_path.iterdir()] == [default_database_in_tmp.parent.name]


def test_the_default_instance_has_no_evidence_store() -> None:
    app, _ = build(Settings())
    assert app.state.evidence is None


# Validation ---------------------------------------------------------------------


def _items_dir(tmp_path: Path, **overrides: object) -> Path:
    directory = tmp_path / "items" / "MAT01-06"
    directory.mkdir(parents=True)
    entry = {
        "id": "t-1",
        "goal": "KM13232",
        "type": "numeric",
        "difficulty": 1,
        "prompt": {"nb": "Hvor mye?", "en": "How much?"},
        "explanation": {"nb": "Så mye.", "en": "That much."},
        "answer": 34,
    } | overrides
    (directory / "KV1021.yaml").write_text(
        yaml.safe_dump({"subject": "MAT01-06", "goal_set": "KV1021", "items": [entry]}),
        encoding="utf-8",
    )
    return tmp_path / "items"


def _about_t1(problems: list[str]) -> list[str]:
    return [p for p in problems if p.startswith("t-1:")]


def test_the_committed_skill_links_validate() -> None:
    assert validate_items() == []


def test_a_skill_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    problems = _about_t1(validate_items(_items_dir(tmp_path, skill="mat.place-value.nope")))
    assert problems and "not in this subject's skills file" in problems[0]


def test_a_skill_that_does_not_cite_the_goal_is_refused(tmp_path: Path) -> None:
    problems = _about_t1(validate_items(_items_dir(tmp_path, skill="mat.counting.subitise")))
    assert problems and "does not cite goal KM13232" in problems[0]


def test_a_skill_practised_off_screen_cannot_be_named(tmp_path: Path) -> None:
    off_screen = next(s for s in mat().skills if not s.assessable and s.checkpoint == 2)
    directory = _items_dir(tmp_path, skill=off_screen.id, goal=off_screen.refs[0])
    problems = _about_t1(validate_items(directory))
    assert any("not assessable" in p for p in problems)


def test_a_sensitive_comment_without_the_field_is_refused(tmp_path: Path) -> None:
    """The old convention is invisible to the code, so it is not allowed back."""
    shutil.copy(DEFAULT_SKILLS_DIR / "MAT01-06.yaml", tmp_path / "MAT01-06.yaml")
    text = (tmp_path / "MAT01-06.yaml").read_text(encoding="utf-8")
    marked = text.replace(
        "  - id: mat.counting.subitise", "  # sensitive: see a note\n  - id: mat.counting.subitise"
    )
    (tmp_path / "MAT01-06.yaml").write_text(marked, encoding="utf-8")
    problems = validate_skills(tmp_path, Catalogue.load())
    assert any("sensitive: true" in p for p in problems)


def test_the_committed_sensitive_skills_carry_the_field() -> None:
    library = SkillLibrary.load()
    sensitive = {
        s.id for code in library.subjects for s in library.for_subject(code).skills if s.sensitive
    }
    assert "nat.body-health.puberty" in sensitive
    assert "saf.history.terrorism-and-genocide" in sensitive
    assert len(sensitive) == 10
