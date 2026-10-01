"""What a drills file may contain.

Two shapes. A pack file, `data/drills/<SUBJECT_CODE>/<GOAL_SET>.yaml`, holds the
fact packs for one goal set, laid out as the item files are. An instruction
set, `data/drills/instructions/<id>.yaml`, says how to quiz, and is shared
between packs.

Both forbid unknown keys, because a misspelt field would otherwise load as a
pack with that field silently missing, and a model would be prompted without
it.

Only what can be judged from one file lives here. Whether the goal exists,
whether the instruction set does, and whether an id is unique across files need
the rest of the data, and are in `validate.py`.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from pensum.items.schema import MAX_DIFFICULTY, MIN_CHOICES
from pensum.items.text import ENGLISH, AuthoredText
from pensum.review.content import reject_review_keys

Filled = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]

# `f1`, `f2` ...: short, because a model has to copy it back to say which fact
# a question was written from, and a long id is one more thing to get wrong.
FactId = Annotated[str, StringConstraints(pattern=r"^f[1-9][0-9]*$")]

# A drill is short (principle 6). The ceiling is on the pack, not only on the
# drill, so that no pack can ask for a batch a pupil would not sit through.
MAX_QUESTIONS = 10

# One right answer and these many wrong ones. The floor is what makes a
# generated question a legal `multiple_choice` item.
MIN_DISTRACTORS = MIN_CHOICES - 1
MAX_DISTRACTORS = 4


class Fact(BaseModel):
    """One sentence that is true on its own, in both UI locales."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: FactId
    nb: Filled
    en: Filled

    @model_validator(mode="after")
    def _one_line(self) -> Fact:
        # A fact is shown to a pupil as the feedback for one question. A
        # paragraph is several facts, and a question cites exactly one.
        for text in (self.nb, self.en):
            if "\n" in text:
                raise ValueError(f"{self.id}: a fact is one sentence, on one line")
        return self

    def get(self, locale: str) -> str:
        return self.en if locale == ENGLISH else self.nb


class FactPack(BaseModel):
    """The facts for one drill, testing one competence goal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Slug
    goal: Filled
    # Relative to the checkpoint, as for an item. Every question written from
    # the pack carries it.
    difficulty: int = Field(ge=1, le=MAX_DIFFICULTY)
    title: AuthoredText
    # The instruction set to quiz by, by id.
    instructions: Slug
    # How many questions one drill asks.
    questions: int = Field(ge=1, le=MAX_QUESTIONS)
    facts: tuple[Fact, ...] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _no_review_keys(cls, data: object) -> object:
        # Review state is not a content field. See `pensum.review.content`.
        return reject_review_keys(data)

    @model_validator(mode="after")
    def _facts_fit_the_drill(self) -> FactPack:
        ids = [fact.id for fact in self.facts]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.id}: fact ids must be unique")
        # One question per fact, so a drill never asks about one fact twice.
        if len(self.facts) < self.questions:
            raise ValueError(
                f"{self.id}: asks for {self.questions} questions from {len(self.facts)} "
                "fact(s); a pack needs at least one fact per question"
            )
        return self

    def fact(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)


class PackFile(BaseModel):
    """Every fact pack authored for one goal set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: Filled
    goal_set: Filled
    packs: tuple[FactPack, ...] = Field(min_length=1)


class InstructionSet(BaseModel):
    """How to quiz. Read by the model, never shown to a pupil.

    Written in English only for that reason: the language a question comes back
    in is a parameter of the request, not a property of these rules.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Slug
    distractors: int = Field(ge=MIN_DISTRACTORS, le=MAX_DISTRACTORS)
    rules: Filled

    @model_validator(mode="before")
    @classmethod
    def _no_review_keys(cls, data: object) -> object:
        return reject_review_keys(data)
