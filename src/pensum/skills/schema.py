"""What a skills file may contain.

One file per subject, `data/skills/<SUBJECT_CODE>.yaml`. The shape is a contract
shared by every subject's author, so the models forbid unknown keys: a typo in a
field name would otherwise load as a skill with that field silently missing.

Only what can be judged from one field at a time lives here. Everything that
needs the rest of the file, or the curriculum, is in `validate.py`, where each
failure can be reported against the rule it breaks rather than as a pydantic
traceback.

The text is ours, and it is keyed `nob`/`eng` rather than by UI locale, which is
why it is not `items.text.AuthoredText`: the file format is fixed and uses the
ISO 639-2 codes Udir's own data uses. `get` translates at the one place a page
reads it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

KEBAB = r"^[a-z0-9]+(-[a-z0-9]+)*$"
# `<subject prefix>.<strand id>.<slug>`. That the middle part really is this
# skill's strand is checked in `validate.py`, which knows the strand.
SKILL_ID = r"^[a-z]+\.[a-z0-9]+(-[a-z0-9]+)*\.[a-z0-9]+(-[a-z0-9]+)*$"

# The short prefix every skill id in a subject starts with. Keyed by the
# subject code, revision and all: a revised curriculum is a new file with new
# goal codes, and deciding its prefix is part of writing it.
PREFIXES = {
    "MAT01-06": "mat",
    "NOR01-08": "nor",
    "ENG01-06": "eng",
    "NAT01-05": "nat",
    "SAF01-05": "saf",
    "RLE01-04": "krle",
}

# Concrete, pictorial, abstract: blocks on the table, a drawing of them, the
# numeral. The order is the order a pupil meets them in, so a skill's list must
# keep it -- `[abstract, concrete]` would read as a progression backwards.
Stage = Literal["concrete", "pictorial", "abstract"]
STAGE_ORDER: tuple[Stage, ...] = ("concrete", "pictorial", "abstract")

Kebab = Annotated[str, StringConstraints(pattern=KEBAB)]
Filled = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SkillText(BaseModel):
    """A string we wrote, in bokmål and English. Neither may be empty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nob: Filled
    eng: Filled

    def get(self, locale: str) -> str:
        """The text for a UI locale. Nynorsk readers get bokmål, as the chrome does."""
        return self.eng if locale == "en" else self.nob


class Strand(BaseModel):
    """One thread of a subject that runs through its checkpoints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Kebab
    title: SkillText


class Skill(BaseModel):
    """One thing a pupil can or cannot yet do, stated so it can be observed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, StringConstraints(pattern=SKILL_ID)]
    strand: Kebab
    checkpoint: int
    refs: tuple[str, ...] = Field(min_length=1)
    needs: tuple[str, ...] = ()
    i_can: SkillText
    teacher: SkillText
    stages: tuple[Stage, ...] = Field(min_length=1)
    misconceptions: tuple[Kebab, ...] = ()
    # False: practised off screen, as a mission, and never quizzed.
    assessable: bool
    # Always false when authored. A human who has read it sets it true.
    reviewed: bool
    # Taught, and therefore in the progression guide, but never a reward and
    # never a cell on the class grid: puberty, abuse, genocide. A teacher does
    # not need to see which pupil got the puberty question wrong, and a pupil
    # should not earn a plant for it. No evidence is recorded against it either;
    # see `pensum.mastery.attribution`. The subject design files say which.
    sensitive: bool = False

    @field_validator("stages")
    @classmethod
    def _stages_in_order(cls, stages: tuple[Stage, ...]) -> tuple[Stage, ...]:
        positions = [STAGE_ORDER.index(stage) for stage in stages]
        if positions != sorted(set(positions)):
            raise ValueError(
                "stages must be distinct and in the order concrete, pictorial, abstract"
            )
        return stages


class SkillFile(BaseModel):
    """Every strand and skill authored for one subject."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: Filled
    strands: tuple[Strand, ...] = Field(min_length=1)
    skills: tuple[Skill, ...] = Field(min_length=1)

    def strand(self, strand_id: str) -> Strand | None:
        return next((s for s in self.strands if s.id == strand_id), None)

    def skill(self, skill_id: str) -> Skill | None:
        return next((s for s in self.skills if s.id == skill_id), None)
