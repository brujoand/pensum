"""Which skills a graded answer is evidence for.

An item that names its `skill` is evidence for exactly that skill; the items
validator has already checked the skill exists, is assessable and cites the
item's goal.

An item that does not is attributed by its goal: to every assessable skill whose
`refs` contain the item's goal and whose checkpoint is the item's goal set. **This
fallback is coarse, and deliberately so rather than accidentally.** One LK20
goal is often three skills (KM13232 is both "build a number with tens and ones"
and "swap ten ones for one ten"), and a numeric question about 34 is evidence
for at most one of them. Attributing it to both makes each look better
evidenced than it is. The alternative -- attributing nothing until every item
names a skill -- would leave every map empty for months. Coarse and visible is
the better failure; tagging items with `skill:` is how it gets precise, one
item at a time.

Sensitive skills are never attributed to, by either route. They are taught and
quizzed factually, but the design keeps them off the map and off the class
grid, and the most reliable way to keep a row off a grid is never to write it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pensum.items.schema import QuizItem
from pensum.scores.evidence import Evidence
from pensum.skills.schema import Skill, SkillFile


def skills_for(item: QuizItem, checkpoint: int, skill_file: SkillFile) -> tuple[Skill, ...]:
    """The skills one answer to `item` counts towards. Often one, sometimes none."""
    if item.skill is not None:
        named = skill_file.skill(item.skill)
        # The validator guarantees it exists; re-checked because a skills file
        # can change between validation and a long-running process's reload.
        if named is None or not named.assessable or named.sensitive:
            return ()
        return (named,)
    return tuple(
        skill
        for skill in skill_file.skills
        if skill.assessable
        and not skill.sensitive
        and skill.checkpoint == checkpoint
        and item.goal in skill.refs
    )


def evidence_for(
    answered: Iterable[tuple[QuizItem, bool]],
    *,
    attempt: str,
    user_sub: str,
    checkpoint: int,
    skill_file: SkillFile,
    at: datetime,
) -> list[Evidence]:
    """One row per (answer, skill) for a finished quiz.

    Every row carries the same timestamp -- when the quiz was finished -- because
    that is when anything is written. Mastery counts sessions as calendar days,
    so a quiz straddling midnight is one session either way.
    """
    return [
        Evidence(
            attempt=attempt,
            user_sub=user_sub,
            skill=skill.id,
            item=item.id,
            stage=item.stage,
            correct=correct,
            # No hint ladder yet: every answer is unaided.
            hints=0,
            recorded_at=at,
        )
        for item, correct in answered
        for skill in skills_for(item, checkpoint, skill_file)
    ]
