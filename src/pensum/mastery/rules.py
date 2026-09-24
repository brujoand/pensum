"""Five mastery states, computed from evidence by rule.

A rule, not a fitted model, for the reason `pensum.quiz.placement` gives: there
is no response data to fit anything to, and a coarse state that is honest about
being coarse beats a decimal ability estimate built on guessed difficulties.

| state       | rule (the defaults in `MasteryRules`)                          |
|-------------|----------------------------------------------------------------|
| not started | no evidence                                                    |
| exploring   | any attempt                                                    |
| practising  | at least one correct answer, hinted or not                     |
| secure      | 4 of the last 5 correct without hints, on at least 2 days, at  |
|             | at least 2 stages including the skill's last                   |
| retained    | secure, then correct without hints at least 7 days later       |

Four readings of the design are choices, and each is stated where it is made:

* **A hinted correct answer is practising.** The design's table says practising
  is "correct without hints", and its rules below the table say "a hinted
  correct answer counts as evidence of practising, not of secure". The second is
  the one about hints, and the kinder one -- hints never fail an attempt -- so it
  wins. Moot until the hint ladder exists: every row has 0 hints today.

* **A session is a calendar day** (UTC). The design says "sessions", and a day
  is the cheapest honest proxy: two quizzes an hour apart are not the spaced
  practice the rule is guarding for, two on different days are.
* **An item with no `stage` counts as the skill's last stage**, and a window
  that relies on one is not held to the two-stage rule, because nothing says
  which representation it used. Almost no item carries a stage yet, so until
  they do, *secure* here is weaker than the design's: it means "right four times
  out of five on two days", not "right with blocks and with numerals".
* **Fewer than five attempts can be secure** if four of them are right. Five is
  the window, not a minimum.

Two states are computed, because the design asks for two. The pupil's map never
goes down: it shows the highest state the evidence has ever reached
(`Mastery.shown`). The teacher's grid shows the state the evidence supports now
(`Mastery.current`), and `Mastery.slipped` is the difference -- a skill to come
back to, which the pupil is never told they have lost.

The thresholds are guesses, to be tuned against the first real classroom data
(open decision 2 in the design). They are a dataclass rather than constants so
a deployment, or a test, can change them without editing this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, timedelta
from enum import IntEnum

from pensum.scores.evidence import Evidence
from pensum.skills.schema import STAGE_ORDER, Skill, Stage


class State(IntEnum):
    """Ordered, so "never goes down" is `max`."""

    NOT_STARTED = 0
    EXPLORING = 1
    PRACTISING = 2
    SECURE = 3
    RETAINED = 4

    @property
    def key(self) -> str:
        """The i18n and CSS name: `not-started`, `exploring` ..."""
        return self.name.lower().replace("_", "-")


@dataclass(frozen=True)
class MasteryRules:
    """The thresholds, with the design's defaults."""

    # Secure: at least `window_correct` of the last `window` answers correct
    # without hints ...
    window: int = 5
    window_correct: int = 4
    # ... on at least this many distinct days ...
    sessions: int = 2
    # ... at at least this many distinct stages, one of them the skill's last.
    # Capped at the number of stages the skill has: a skill taught only with
    # numerals cannot be shown at two stages.
    stages: int = 2
    # Retained: a correct, unhinted answer at least this long after the skill
    # first became secure.
    retention: timedelta = timedelta(days=7)


DEFAULT_RULES = MasteryRules()


@dataclass(frozen=True)
class Mastery:
    """What one pupil's evidence on one skill adds up to."""

    current: State
    shown: State
    # Stages at which the pupil has answered correctly (hinted or not), in
    # stage order. What "the representation stage last reached" is read from.
    stages_reached: tuple[Stage, ...] = ()
    # Whether any correct answer came from an item with no stage. Kept apart
    # from `stages_reached` so the grid can say "not recorded" rather than
    # pretending an unstaged item was abstract.
    unstaged_correct: bool = False

    @property
    def slipped(self) -> bool:
        """The evidence supports less now than it once did. For the teacher only."""
        return self.shown > self.current

    @property
    def furthest_stage(self) -> Stage | None:
        return self.stages_reached[-1] if self.stages_reached else None

    @property
    def concrete_only(self) -> bool:
        """Practising, and only ever right with objects: the cell a teacher wants.

        The pupil can do it with blocks and has not yet moved to a drawing or
        numerals. An unstaged correct answer rules it out, since it might have
        been either.
        """
        return (
            self.current == State.PRACTISING
            and self.stages_reached == ("concrete",)
            and not self.unstaged_correct
        )


NOT_STARTED = Mastery(current=State.NOT_STARTED, shown=State.NOT_STARTED)


def _day(row: Evidence) -> date:
    return row.recorded_at.astimezone(UTC).date()


def _clean(row: Evidence) -> bool:
    """Correct without hints: the only answer that counts towards secure."""
    return row.correct and row.hints == 0


def is_secure(rows: Sequence[Evidence], skill: Skill, rules: MasteryRules = DEFAULT_RULES) -> bool:
    """Whether the last `window` answers meet the secure rule. `rows` oldest first."""
    clean = [row for row in rows[-rules.window :] if _clean(row)]
    if len(clean) < rules.window_correct:
        return False
    if len({_day(row) for row in clean}) < rules.sessions:
        return False

    last = skill.stages[-1]
    stages = {row.stage or last for row in clean}
    if last not in stages:
        return False
    unstaged = any(row.stage is None for row in clean)
    return unstaged or len(stages) >= min(rules.stages, len(skill.stages))


def assess(rows: Sequence[Evidence], skill: Skill, rules: MasteryRules = DEFAULT_RULES) -> Mastery:
    """The mastery of one skill, from its evidence, oldest first.

    Walks the evidence in order, because two things depend on history rather
    than on the current window: when the skill first became secure (which the
    retention check is timed from), and the highest state ever reached (which
    the pupil's map shows).
    """
    if not rows:
        return NOT_STARTED

    secure_since = None
    retained = False
    for index, row in enumerate(rows):
        # The spaced check is judged before this row can make the skill secure:
        # one answer cannot be both the fourth correct and the check a week on.
        if (
            secure_since is not None
            and not retained
            and _clean(row)
            and row.recorded_at - secure_since >= rules.retention
        ):
            retained = True
        if secure_since is None and is_secure(rows[: index + 1], skill, rules):
            secure_since = row.recorded_at

    base = State.PRACTISING if any(row.correct for row in rows) else State.EXPLORING
    if is_secure(rows, skill, rules):
        current = State.RETAINED if retained else State.SECURE
    else:
        current = base

    if retained:
        shown = State.RETAINED
    elif secure_since is not None:
        shown = State.SECURE
    else:
        shown = base

    reached = {row.stage for row in rows if row.correct and row.stage is not None}
    return Mastery(
        current=current,
        # `max` is belt and braces: `shown` is built from history and already
        # cannot be below `current`, and this is the one invariant a pupil sees.
        shown=max(shown, current),
        stages_reached=tuple(stage for stage in STAGE_ORDER if stage in reached),
        unstaged_correct=any(row.correct and row.stage is None for row in rows),
    )
