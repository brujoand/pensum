"""Everything an administrator could be asked to approve, in one list.

The content kinds are authored in different shapes and served by different
routes, but a reviewer's question is the same for all of them -- is this fit for
a pupil here -- so the queue flattens them into one row shape and lets the
template pick a renderer per kind.

A template is one row, not one per instance. It is decided as a unit, because
that is how it is served (`ItemBank.for_goal_set` asks about the template) and
because a rule that produces two hundred questions is read as a rule. The page
shows one instance live and a sample of the others with their answers.

The libraries hold every authored piece in memory whatever its state; the
filtering happens at access time. That is what makes this cheap: walking the
queue reads what is already loaded and asks the ledger a dict question per row.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from pensum.auth.models import User
from pensum.catalogue.loader import Catalogue
from pensum.items.loader import ItemBank
from pensum.items.schema import QuizItem
from pensum.items.template import ItemTemplate
from pensum.missions.loader import MissionLibrary
from pensum.missions.schema import Mission
from pensum.reading.library import ReadingLibrary
from pensum.reading.schema import ReadingText
from pensum.review.store import KINDS, STATES, Decision, Kind, ReviewLedger, State, Verdict
from pensum.skills.loader import SkillLibrary
from pensum.skills.schema import Skill
from pensum.writing.library import WritingLibrary
from pensum.writing.schema import WritingPrompt

Content = QuizItem | ItemTemplate | ReadingText | WritingPrompt | Skill | Mission

# "all" is the absence of a filter, spelled the way the page's links spell it.
ALL = "all"


@dataclass(frozen=True)
class ReviewEntry:
    """One piece of content, with everything the review page needs about it."""

    kind: Kind
    content_id: str
    subject: str
    # The goal set it belongs to. For a skill or mission, the goal set at its
    # checkpoint; empty only where the catalogue no longer has one.
    goal_set: str
    title: str
    fingerprint: str
    decision: Decision | None
    content: Content
    goal: str | None = None
    difficulty: int | None = None

    @property
    def state(self) -> State:
        if self.decision is None:
            return "pending"
        return self.decision.state_for(self.fingerprint)

    @property
    def is_template(self) -> bool:
        return isinstance(self.content, ItemTemplate)

    @property
    def anchor(self) -> str:
        """An HTML id for the row. A template id has no `#`, but be sure."""
        return f"{self.kind}-{self.content_id}".replace("#", "-")


@dataclass(frozen=True)
class Libraries:
    """What the queue is built from. The same objects the app serves from."""

    items: ItemBank
    reading: ReadingLibrary
    writing: WritingLibrary
    skills: SkillLibrary
    missions: MissionLibrary


def _title_of(content: Content) -> str:
    """A short label for a row, in bokmål: the language every piece is authored in.

    Quiz items have no title -- they have a prompt, in two languages -- so the
    bokmål prompt stands in. Truncating is the template's business.
    """
    if isinstance(content, QuizItem | ItemTemplate):
        return content.prompt.get("nb")
    if isinstance(content, Skill):
        return content.i_can.nob
    if isinstance(content, Mission):
        return content.title.nob
    return content.title


def entries(
    libraries: Libraries,
    ledger: ReviewLedger | None = None,
    catalogue: Catalogue | None = None,
) -> list[ReviewEntry]:
    """Every authored piece of content, whatever its state.

    Ordered by kind, then by the checkpoint it belongs to, then by the order it
    appears in its file -- which is the order a human authored it in, and so the
    order it reads in.
    """
    decisions = ledger.decisions() if ledger is not None else {}
    collected: list[ReviewEntry] = []

    def add(
        kind: Kind,
        subject: str,
        goal_set: str,
        content: Content,
        fingerprint: str | None,
        *,
        goal: str | None = None,
        difficulty: int | None = None,
    ) -> None:
        if fingerprint is None:  # pragma: no cover -- every id came from the library
            return
        collected.append(
            ReviewEntry(
                kind=kind,
                content_id=content.id,
                subject=subject,
                goal_set=goal_set,
                title=_title_of(content),
                fingerprint=fingerprint,
                decision=decisions.get((kind, content.id)),
                content=content,
                goal=goal,
                difficulty=difficulty,
            )
        )

    items = libraries.items
    for item_set in items.item_sets:
        for item in item_set.items:
            add(
                "item",
                item_set.subject,
                item_set.goal_set,
                item,
                items.fingerprint(item.id),
                goal=item.goal,
                difficulty=item.difficulty,
            )
        for template in item_set.templates:
            add(
                "item",
                item_set.subject,
                item_set.goal_set,
                template,
                items.fingerprint(template.id),
                goal=template.goal,
                difficulty=template.difficulty,
            )
    for reading_set in libraries.reading.reading_sets:
        for text in reading_set.texts:
            add(
                "reading",
                reading_set.subject,
                reading_set.goal_set,
                text,
                libraries.reading.fingerprint(text.id),
                goal=text.goal,
                difficulty=text.difficulty,
            )
    for writing_set in libraries.writing.writing_sets:
        for prompt in writing_set.prompts:
            add(
                "writing",
                writing_set.subject,
                writing_set.goal_set,
                prompt,
                libraries.writing.fingerprint(prompt.id),
                goal=prompt.goal,
                difficulty=prompt.difficulty,
            )

    checkpoints: dict[str, int] = {}
    for subject_code in libraries.skills.subjects:
        skill_file = libraries.skills.for_subject(subject_code)
        if skill_file is None:  # pragma: no cover -- listed by the library itself
            continue
        for skill in skill_file.skills:
            checkpoints[skill.id] = skill.checkpoint
            add(
                "skill",
                subject_code,
                _goal_set_at(catalogue, subject_code, skill.checkpoint),
                skill,
                libraries.skills.fingerprint(skill.id),
            )
    for subject_code in libraries.missions.subjects:
        mission_file = libraries.missions.for_subject(subject_code)
        if mission_file is None:
            continue
        for mission in mission_file.missions:
            checkpoint = checkpoints.get(mission.skill)
            add(
                "mission",
                subject_code,
                _goal_set_at(catalogue, subject_code, checkpoint) if checkpoint else "",
                mission,
                libraries.missions.fingerprint(mission.id),
            )

    return collected


def _goal_set_at(catalogue: Catalogue | None, subject_code: str, checkpoint: int) -> str:
    if catalogue is None:
        return ""
    subject = catalogue.subject(subject_code)
    if subject is None:
        return ""
    return next((gs.code for gs in subject.goal_sets if gs.after_year == checkpoint), "")


@dataclass(frozen=True)
class Filters:
    """What the page is narrowed to. Every field is either a value or `ALL`."""

    subject: str = ALL
    goal_set: str = ALL
    kind: str = ALL
    state: str = "pending"

    @classmethod
    def parse(cls, subject: str, goal_set: str, kind: str, state: str) -> Filters:
        """Unknown values fall back rather than error: these come from a URL."""
        return cls(
            subject=subject or ALL,
            goal_set=goal_set or ALL,
            kind=kind if kind in KINDS else ALL,
            state=state if state in STATES else ALL,
        )

    def matches(self, entry: ReviewEntry) -> bool:
        return (
            (self.subject == ALL or entry.subject == self.subject)
            and (self.goal_set == ALL or entry.goal_set == self.goal_set)
            and (self.kind == ALL or entry.kind == self.kind)
            and (self.state == ALL or entry.state == self.state)
        )

    def query(self, **overrides: str) -> str:
        """The query string for these filters, with any overridden."""
        values = {
            "subject": self.subject,
            "goal_set": self.goal_set,
            "kind": self.kind,
            "state": self.state,
        } | overrides
        return urlencode(values)


def select(collected: Iterable[ReviewEntry], filters: Filters) -> list[ReviewEntry]:
    return [entry for entry in collected if filters.matches(entry)]


def digest(selected: Iterable[ReviewEntry]) -> str:
    """A short hash of exactly which content, in exactly which version, is selected.

    Carried through the bulk confirmation step, so that what is applied is what
    was counted: if anything was edited, approved by someone else or added in
    between, the digest no longer matches and nothing is written.
    """
    parts = sorted(f"{e.kind}:{e.content_id}:{e.fingerprint}" for e in selected)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:32]


def decide(
    selected: Iterable[ReviewEntry],
    verdict: Verdict,
    user: User,
    note: str | None = None,
    *,
    now: datetime | None = None,
) -> list[Decision]:
    """The decisions that approve or reject each of these, as they are now."""
    at = now or datetime.now(UTC)
    return [
        Decision(
            kind=entry.kind,
            content_id=entry.content_id,
            verdict=verdict,
            by_sub=user.sub,
            by_name=user.name,
            decided_at=at,
            note=note,
            fingerprint=entry.fingerprint,
        )
        for entry in selected
    ]


@dataclass(frozen=True)
class Counts:
    """How much is in each state."""

    pending: int
    approved: int
    rejected: int
    changed: int

    @property
    def total(self) -> int:
        return self.pending + self.approved + self.rejected + self.changed


def counts(collected: Iterable[ReviewEntry]) -> Counts:
    tally = dict.fromkeys(STATES, 0)
    for entry in collected:
        tally[entry.state] += 1
    return Counts(**tally)


def find(collected: Iterable[ReviewEntry], kind: str, content_id: str) -> ReviewEntry | None:
    return next(
        (e for e in collected if e.kind == kind and e.content_id == content_id),
        None,
    )
