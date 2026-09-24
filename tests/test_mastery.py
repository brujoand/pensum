"""The mastery rules, driven by constructed evidence sequences.

No database and no app: `pensum.mastery.rules` is a pure function of the rows,
so every rule in the design's table gets a sequence that just meets it and one
that just misses it. The invariant the pupil sees -- the map never goes down --
is asserted on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pensum.mastery.rules import MasteryRules, State, assess, is_secure
from pensum.scores.evidence import Evidence
from pensum.skills.schema import Skill

START = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def skill(stages: tuple[str, ...] = ("concrete", "pictorial", "abstract")) -> Skill:
    return Skill.model_validate(
        {
            "id": "mat.place-value.exchange-tens",
            "strand": "place-value",
            "checkpoint": 2,
            "refs": ["KM13232"],
            "i_can": {"nob": "Jeg kan bytte.", "eng": "I can swap."},
            "teacher": {"nob": "Bytter.", "eng": "Swaps."},
            "stages": list(stages),
            "assessable": True,
            "reviewed": False,
        }
    )


def ev(
    day: float,
    correct: bool = True,
    stage: str | None = "abstract",
    hints: int = 0,
) -> Evidence:
    return Evidence(
        attempt=f"a{day}",
        user_sub="u-1",
        skill="mat.place-value.exchange-tens",
        item=f"i{day}",
        stage=stage,  # type: ignore[arg-type]
        correct=correct,
        hints=hints,
        recorded_at=START + timedelta(days=day),
    )


def secure_run(start: float = 0) -> list[Evidence]:
    """Four clean answers on two days, concrete then abstract: just secure."""
    return [
        ev(start, stage="concrete"),
        ev(start, stage="concrete"),
        ev(start + 1, stage="abstract"),
        ev(start + 1, stage="abstract"),
    ]


# The five states ---------------------------------------------------------------


def test_no_evidence_is_not_started() -> None:
    mastery = assess([], skill())
    assert mastery.current == mastery.shown == State.NOT_STARTED


def test_any_attempt_is_exploring() -> None:
    mastery = assess([ev(0, correct=False)], skill())
    assert mastery.current == mastery.shown == State.EXPLORING


def test_one_correct_answer_is_practising() -> None:
    mastery = assess([ev(0, correct=False), ev(0)], skill())
    assert mastery.current == State.PRACTISING


def test_a_hinted_correct_answer_is_practising_but_never_secure() -> None:
    """Hints never fail an attempt, and never make one count towards secure."""
    hinted = [ev(0, stage="concrete", hints=1), ev(1, stage="abstract", hints=2)] * 3
    mastery = assess(hinted, skill())
    assert mastery.current == State.PRACTISING
    assert not is_secure(hinted, skill())


def test_four_clean_answers_on_two_days_at_two_stages_is_secure() -> None:
    mastery = assess(secure_run(), skill())
    assert mastery.current == mastery.shown == State.SECURE


def test_four_of_the_last_five_is_enough() -> None:
    rows = [*secure_run(), ev(1, correct=False)]
    assert assess(rows, skill()).current == State.SECURE


def test_three_of_the_last_five_is_not() -> None:
    rows = [*secure_run()[:3], ev(1, correct=False), ev(1, correct=False)]
    assert assess(rows, skill()).current == State.PRACTISING


def test_only_the_last_five_count() -> None:
    """Old mistakes fall out of the window; a pupil is not held to last month."""
    rows = [ev(0, correct=False)] * 6 + secure_run(start=1)
    assert assess(rows, skill()).current == State.SECURE


def test_one_day_is_not_enough() -> None:
    """Straight after a worked example is short-term memory."""
    rows = [ev(0, stage="concrete")] * 2 + [ev(0, stage="abstract")] * 2
    assert assess(rows, skill()).current == State.PRACTISING


def test_two_quizzes_on_one_calendar_day_are_one_session() -> None:
    rows = [ev(0, stage="concrete")] * 2 + [ev(0.4, stage="abstract")] * 2
    assert assess(rows, skill()).current == State.PRACTISING


def test_one_stage_is_not_enough() -> None:
    """Can do it with blocks but not with numerals is not yet secure."""
    rows = [ev(0, stage="concrete")] * 2 + [ev(1, stage="concrete")] * 2
    mastery = assess(rows, skill())
    assert mastery.current == State.PRACTISING


def test_two_stages_must_include_the_skills_last() -> None:
    rows = [ev(0, stage="concrete")] * 2 + [ev(1, stage="pictorial")] * 2
    assert assess(rows, skill()).current == State.PRACTISING


def test_a_single_stage_skill_needs_only_its_one_stage() -> None:
    rows = [ev(0, stage="abstract")] * 2 + [ev(1, stage="abstract")] * 2
    assert assess(rows, skill(("abstract",))).current == State.SECURE


def test_an_unstaged_item_counts_as_the_last_stage_and_waives_the_second() -> None:
    """The documented weakening: until items carry stages, secure is easier."""
    rows = [ev(0, stage=None)] * 2 + [ev(1, stage=None)] * 2
    assert assess(rows, skill()).current == State.SECURE


def test_an_unstaged_item_supplies_the_last_stage() -> None:
    rows = [ev(0, stage="concrete")] * 2 + [ev(1, stage=None)] * 2
    assert assess(rows, skill()).current == State.SECURE


def test_retained_needs_a_clean_answer_a_week_after_secure() -> None:
    rows = [*secure_run(), ev(8)]
    mastery = assess(rows, skill())
    assert mastery.current == mastery.shown == State.RETAINED


def test_exactly_seven_days_is_a_week() -> None:
    # secure_run becomes secure on day 1.
    assert assess([*secure_run(), ev(8)], skill()).current == State.RETAINED
    assert assess([*secure_run(), ev(7.9)], skill()).current == State.SECURE


def test_a_hinted_check_is_not_a_retention_check() -> None:
    rows = [*secure_run(), ev(9, hints=1)]
    assert assess(rows, skill()).shown == State.SECURE


def test_the_answer_that_makes_it_secure_is_not_also_the_check() -> None:
    """Secure on day 10 after a first answer on day 0: no check has happened yet."""
    rows = [ev(0, stage="concrete"), ev(10, stage="concrete"), ev(10), ev(10)]
    assert assess(rows, skill()).current == State.SECURE


# Never goes down on screen ------------------------------------------------------


def test_the_pupils_state_never_goes_down_but_the_teachers_does() -> None:
    rows = [*secure_run(), ev(2, correct=False), ev(2, correct=False)]
    mastery = assess(rows, skill())
    assert mastery.shown == State.SECURE
    assert mastery.current == State.PRACTISING
    assert mastery.slipped


def test_a_retained_skill_that_fails_later_stays_a_flower_for_the_pupil() -> None:
    rows = [*secure_run(), ev(9), *[ev(20, correct=False)] * 3]
    mastery = assess(rows, skill())
    assert mastery.shown == State.RETAINED
    assert mastery.current == State.PRACTISING


@pytest.mark.parametrize("length", range(12))
def test_shown_is_monotonic_over_any_prefix(length: int) -> None:
    """Replay a bumpy history one answer at a time: the map never shrinks."""
    history = [
        ev(0, correct=False),
        *secure_run(start=1),
        ev(3, correct=False),
        ev(3, correct=False),
        ev(12),
        ev(13, correct=False),
        ev(13, correct=False),
        ev(13, correct=False),
    ]
    before = assess(history[:length], skill()).shown
    after = assess(history[: length + 1], skill()).shown
    assert after >= before
    assert assess(history[:length], skill()).shown >= assess(history[:length], skill()).current


# What the grid reads ------------------------------------------------------------


def test_concrete_only_is_practising_with_objects_and_nothing_else() -> None:
    rows = [ev(0, stage="concrete"), ev(0, correct=False, stage="abstract")]
    mastery = assess(rows, skill())
    assert mastery.concrete_only
    assert mastery.furthest_stage == "concrete"


def test_concrete_only_is_ruled_out_by_an_unstaged_correct_answer() -> None:
    rows = [ev(0, stage="concrete"), ev(0, stage=None)]
    mastery = assess(rows, skill())
    assert not mastery.concrete_only
    assert mastery.unstaged_correct


def test_furthest_stage_is_the_most_advanced_correct_one() -> None:
    rows = [ev(0, stage="pictorial"), ev(0, stage="concrete"), ev(0, correct=False)]
    assert assess(rows, skill()).stages_reached == ("concrete", "pictorial")
    assert assess(rows, skill()).furthest_stage == "pictorial"


# Configuration ------------------------------------------------------------------


def test_the_thresholds_are_configuration() -> None:
    lenient = MasteryRules(window=3, window_correct=2, sessions=1, stages=1)
    rows = [ev(0), ev(0)]
    assert assess(rows, skill(), lenient).current == State.SECURE
    assert assess(rows, skill()).current == State.PRACTISING


def test_the_retention_gap_is_configuration() -> None:
    quick = MasteryRules(retention=timedelta(days=1))
    rows = [*secure_run(), ev(2)]
    assert assess(rows, skill(), quick).current == State.RETAINED


def test_state_keys_match_the_i18n_and_css_names() -> None:
    assert [s.key for s in State] == [
        "not-started",
        "exploring",
        "practising",
        "secure",
        "retained",
    ]
