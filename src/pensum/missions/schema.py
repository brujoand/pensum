"""What a missions file may contain.

One file per subject, `data/missions/<SUBJECT_CODE>.yaml`, beside the skills
file it serves. As there, the models forbid unknown keys, because a misspelt
field would otherwise load as a mission with that field silently missing.

Only what can be judged from one field lives here. Whether the skill exists,
whether it is off screen, how many steps there are and whether the id is unique
need the rest of the data, and are in `validate.py`, where each failure names
the rule it breaks.

The text reuses `SkillText`: the same authored `nob`/`eng` pair, for the same
reason, and read through the same `get`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from pensum.skills.schema import Filled, SkillText

# `<subject prefix>.<slug>`: flat, because a mission is filed under its skill
# and does not need a strand in its name. That the prefix is this subject's is
# checked in `validate.py`, against the same table skill ids use.
MISSION_ID = r"^[a-z]+\.[a-z0-9]+(-[a-z0-9]+)*$"

# The printable scripts. A fixed set on purpose: a card is a structure a pupil
# learns once and meets again in every subject, and a new kind per mission would
# undo exactly the predictability it exists for. The wording of each is in the
# locale files, under `missions.card.<kind>`, and its shape in `cards.py`.
CardKind = Literal[
    "turn",
    "feedback",
    "question",
    "ladder",
    "interview",
    "risk",
    "solve_it",
    "method",
    "checklist",
]

# Who says the mission is done. Only a teacher's word will ever move mastery
# past practising; a pupil's own tick is still worth having.
Confirm = Literal["teacher", "self"]


class Mission(BaseModel):
    """One off-screen task for one skill, in a few steps a pupil can tick."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, StringConstraints(pattern=MISSION_ID)]
    skill: Filled
    title: SkillText
    steps: tuple[SkillText, ...] = Field(min_length=1)
    confirm: Confirm
    card: CardKind | None = None
    # The open question a question card prints large. Required exactly when the
    # card is a question card, which `validate.py` checks.
    question: SkillText | None = None
    # Always false when authored. A human who has read it sets it true.
    reviewed: bool


class MissionFile(BaseModel):
    """Every mission authored for one subject."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: Filled
    missions: tuple[Mission, ...] = Field(min_length=1)

    def mission(self, mission_id: str) -> Mission | None:
        return next((m for m in self.missions if m.id == mission_id), None)
