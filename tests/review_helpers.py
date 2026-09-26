"""Approving content in a test the way an instance does: through the ledger.

There is no flag in any file to set. A test that needs content served to a
pupil records an approval for it in a review store, exactly as the review page
does, with the fingerprint of the content as it is loaded -- so these helpers
exercise the real gate rather than stepping around it.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from pensum.items.loader import ItemBank
from pensum.missions.loader import MissionLibrary
from pensum.reading.library import ReadingLibrary
from pensum.review.store import Decision, Kind, ReviewLedger, ReviewStore
from pensum.skills.loader import SkillLibrary
from pensum.writing.library import WritingLibrary

REVIEWER_SUB = "test-reviewer"
REVIEWER_NAME = "Testperson"


def decision(
    kind: Kind, content_id: str, fingerprint: str | None, verdict: str = "approved"
) -> Decision:
    return Decision(
        kind=kind,
        content_id=content_id,
        verdict=verdict,  # type: ignore[arg-type]
        by_sub=REVIEWER_SUB,
        by_name=REVIEWER_NAME,
        decided_at=datetime.now(UTC),
        fingerprint=fingerprint,
    )


def approve_all(
    ledger: ReviewLedger,
    *,
    items: ItemBank | None = None,
    reading: ReadingLibrary | None = None,
    writing: WritingLibrary | None = None,
    skills: SkillLibrary | None = None,
    missions: MissionLibrary | None = None,
) -> int:
    """Approve every piece of content in the given libraries, and attach the ledger.

    Returns how many decisions were written.
    """
    decisions: list[Decision] = []
    if items is not None:
        items.with_ledger(ledger)
        for item_set in items.item_sets:
            for piece in (*item_set.items, *item_set.templates):
                decisions.append(decision("item", piece.id, items.fingerprint(piece.id)))
    if reading is not None:
        reading.with_ledger(ledger)
        for reading_set in reading.reading_sets:
            for text in reading_set.texts:
                decisions.append(decision("reading", text.id, reading.fingerprint(text.id)))
    if writing is not None:
        writing.with_ledger(ledger)
        for writing_set in writing.writing_sets:
            for prompt in writing_set.prompts:
                decisions.append(decision("writing", prompt.id, writing.fingerprint(prompt.id)))
    if skills is not None:
        skills.with_ledger(ledger)
        for subject in skills.subjects:
            skill_file = skills.for_subject(subject)
            assert skill_file is not None
            for skill in skill_file.skills:
                decisions.append(decision("skill", skill.id, skills.fingerprint(skill.id)))
    if missions is not None:
        missions.with_ledger(ledger)
        for subject in missions.subjects:
            mission_file = missions.for_subject(subject)
            assert mission_file is not None
            for mission in mission_file.missions:
                decisions.append(decision("mission", mission.id, missions.fingerprint(mission.id)))
    written = ledger.store.record_many(decisions)
    ledger.reload()
    return written


def ledger_at(path: Path) -> ReviewLedger:
    """A fresh ledger over a fresh store at `path`."""
    return ReviewLedger(ReviewStore(path))


def approved_bank(path: Path, bank: ItemBank | None = None) -> ItemBank:
    """An item bank with every item approved, for tests that only need items served."""
    bank = bank if bank is not None else ItemBank.load()
    approve_all(ledger_at(path), items=bank)
    return bank


def approve_app(app: FastAPI) -> int:
    """Approve everything an app serves, through its own ledger.

    For a test about something other than review: the pages under test should
    behave as they do on an instance where an administrator has approved all
    the content. Missions are loaded here if the app has not loaded them yet,
    exactly as the first request would.
    """
    state = app.state
    missions = getattr(state, "missions", None)
    if missions is None:
        missions = MissionLibrary.load()
        state.missions = missions
    return approve_all(
        state.reviews,
        items=state.items,
        reading=state.reading,
        writing=state.writing,
        skills=state.skills,
        missions=missions,
    )


def approved[Library: (ItemBank, ReadingLibrary, WritingLibrary, SkillLibrary, MissionLibrary)](
    library: Library,
) -> Library:
    """The same library, with everything in it approved through a throwaway ledger.

    For a test that reads content through the serving path (`for_goal_set`,
    `has_quiz`, a listening round) and is about something other than review.
    """
    directory = tempfile.mkdtemp(prefix="pensum-review-")
    atexit.register(shutil.rmtree, directory, True)
    path = Path(directory) / "db.sqlite"
    keyword = {
        ItemBank: "items",
        ReadingLibrary: "reading",
        WritingLibrary: "writing",
        SkillLibrary: "skills",
        MissionLibrary: "missions",
    }[type(library)]
    approve_all(ledger_at(path), **{keyword: library})
    return library
