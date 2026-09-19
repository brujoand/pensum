"""One checkpoint's worth of questions: the file, rather than the question.

Its own module, and not part of the item schema, for the same dull structural
reason `text.py` is: a set holds both hand-written items and templates, a
template builds items, and a module cannot import the module that imports it.
`schema.py` therefore knows nothing about templates, `template.py` knows about
items, and this file is where the two meet.

A set is also where the two kinds of honesty about a goal live side by side. A
goal is either tested, by an item or a template, or it is recorded in
`not_assessable` with a reason somebody signed. What must never happen is a goal
that is simply absent, because an absent goal reads as an oversight and a
recorded one reads as a decision.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.items.schema import QuizItem
from pensum.items.template import ItemTemplate

__all__ = ["ItemSet", "NotAssessable"]


class NotAssessable(BaseModel):
    """A goal deliberately left unquizzed, and why.

    Recorded rather than omitted so the gap is visible: an absent goal looks
    like an oversight, whereas this is a judgement someone made and signed.
    """

    model_config = ConfigDict(frozen=True)

    goal: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ItemSet(BaseModel):
    """Every item authored for one goal set. One file per checkpoint."""

    model_config = ConfigDict(frozen=True)

    subject: str = Field(min_length=1)
    goal_set: str = Field(min_length=1)
    items: tuple[QuizItem, ...] = ()
    # Questions written once and asked with different numbers each time. A
    # template is not an item and never serves as one: `ItemBank` instantiates
    # it, and what reaches a pupil is an ordinary `QuizItem`.
    templates: tuple[ItemTemplate, ...] = ()
    not_assessable: tuple[NotAssessable, ...] = ()

    @model_validator(mode="after")
    def _check_no_duplicate_ids(self) -> ItemSet:
        # Templates share the namespace because their instances carry the
        # template's id as a prefix. Two things with one id would produce
        # instances nothing could tell apart, including the score store.
        ids = [item.id for item in self.items] + [template.id for template in self.templates]
        if len(set(ids)) != len(ids):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"{self.goal_set}: duplicate item ids {duplicates}")
        return self

    @property
    def goals_covered(self) -> set[str]:
        return {item.goal for item in self.items} | {t.goal for t in self.templates}

    @property
    def goals_excused(self) -> set[str]:
        return {entry.goal for entry in self.not_assessable}
