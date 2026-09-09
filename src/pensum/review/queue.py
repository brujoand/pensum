"""Everything a human could be asked to sign off, in one list.

The three content types are authored in different shapes and served by different
routes, but a reviewer's question is the same for all of them -- is this fit for
a child to see -- so the queue flattens them into one row shape and lets the
template pick a renderer per kind.

The libraries hold every authored piece in memory regardless of its flag; the
filtering happens at access time. That is what makes this cheap: walking the
queue reads what is already loaded and asks the ledger a dict question per row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pensum.items.loader import ItemBank
from pensum.items.schema import QuizItem
from pensum.reading.library import ReadingLibrary
from pensum.reading.schema import ReadingText
from pensum.review.store import Decision, Kind, ReviewLedger
from pensum.writing.library import WritingLibrary
from pensum.writing.schema import WritingPrompt

# What the reviewer is looking at, once the file flag and any decision are
# combined. `pending` is the queue proper; the other two are the archive.
State = Literal["pending", "published", "rejected"]

Content = QuizItem | ReadingText | WritingPrompt


@dataclass(frozen=True)
class ReviewEntry:
    """One piece of content, with everything the review page needs about it."""

    kind: Kind
    content_id: str
    subject: str
    goal_set: str
    goal: str
    title: str
    difficulty: int
    file_reviewed: bool
    decision: Decision | None
    content: Content

    @property
    def published(self) -> bool:
        """Whether a pupil can see this right now."""
        if self.decision is None:
            return self.file_reviewed
        return self.decision.approved

    @property
    def state(self) -> State:
        if self.decision is not None:
            return "published" if self.decision.approved else "rejected"
        return "published" if self.file_reviewed else "pending"

    @property
    def overridden(self) -> bool:
        """Whether the decision disagrees with the file it concerns.

        Worth showing: these are the rows where the repository and the running
        site say different things, and they are the ones a maintainer will want
        to settle in the files eventually.
        """
        return self.decision is not None and self.decision.approved != self.file_reviewed


def _title_of(content: Content) -> str:
    """A short label for a row.

    Quiz items have no title -- they have a prompt, in two languages -- so the
    bokmaal prompt stands in. Truncating is the template's business; a reviewer
    scanning the list needs enough to recognise the question.
    """
    if isinstance(content, QuizItem):
        return content.prompt.get("nb")
    return content.title


def entries(
    items: ItemBank,
    reading: ReadingLibrary,
    writing: WritingLibrary,
    ledger: ReviewLedger | None = None,
) -> list[ReviewEntry]:
    """Every authored piece of content, whatever its state.

    Ordered by kind, then by the checkpoint it belongs to, then by the order it
    appears in its file -- which is the order a human authored it in, and so the
    order it reads in.
    """
    decisions = ledger.decisions() if ledger is not None else {}
    collected: list[ReviewEntry] = []

    def add(kind: Kind, subject: str, goal_set: str, content: Content) -> None:
        collected.append(
            ReviewEntry(
                kind=kind,
                content_id=content.id,
                subject=subject,
                goal_set=goal_set,
                goal=content.goal,
                title=_title_of(content),
                difficulty=content.difficulty,
                file_reviewed=content.reviewed,
                decision=decisions.get((kind, content.id)),
                content=content,
            )
        )

    for item_set in items.item_sets:
        for item in item_set.items:
            add("item", item_set.subject, item_set.goal_set, item)
    for reading_set in reading.reading_sets:
        for text in reading_set.texts:
            add("reading", reading_set.subject, reading_set.goal_set, text)
    for writing_set in writing.writing_sets:
        for prompt in writing_set.prompts:
            add("writing", writing_set.subject, writing_set.goal_set, prompt)

    return collected


@dataclass(frozen=True)
class Counts:
    """How much is waiting, and how much has been decided."""

    pending: int
    published: int
    rejected: int

    @property
    def total(self) -> int:
        return self.pending + self.published + self.rejected


def counts(collected: list[ReviewEntry]) -> Counts:
    return Counts(
        pending=sum(1 for entry in collected if entry.state == "pending"),
        published=sum(1 for entry in collected if entry.state == "published"),
        rejected=sum(1 for entry in collected if entry.state == "rejected"),
    )


def find(collected: list[ReviewEntry], kind: str, content_id: str) -> ReviewEntry | None:
    return next(
        (e for e in collected if e.kind == kind and e.content_id == content_id),
        None,
    )
