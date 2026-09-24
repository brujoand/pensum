"""Evidence: one row per graded answer, filed under the skill it shows.

The attempt store keeps what a pupil's result page shows -- a score and a tally
per goal. Mastery needs a little more than that and much less than a
transcript: for each answer, which skill it counts towards, which item it was,
the representation stage the item asked for, whether it was right, and how many
hints were used. That is the whole row. Not the response the pupil gave, not how
long they took, not the order they clicked in.

The item id is kept, and it is the one field that needs a reason: it is what
lets a teacher see that "wrong on the place-value skill" means wrong on the same
question three times, rather than on three different ones. It does not say what
the pupil answered.

Same gate as the attempt store, and the same file. Rows are written only when a
signed-in pupil finishes a quiz on an instance with a database -- at the moment
the attempt summary is written, never before -- so an abandoned quiz leaves no
evidence either, and an anonymous one never has anybody to file it under.

Hints are always 0 until the hint ladder exists (the run engine, a later
change). The column is there now so that mastery's rule "a hinted answer is
evidence of practising, not of secure" has something to read the day it does.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pensum.items.primitives.base import Stage
from pensum.scores.store import connect

# A new table in the same file, created on open exactly as `attempts` is. There
# is no migration step because there is no earlier shape of this table to
# migrate from; an existing database simply gains it on the next start.
SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    attempt     TEXT NOT NULL,
    user_sub    TEXT NOT NULL,
    skill       TEXT NOT NULL,
    item        TEXT NOT NULL,
    stage       TEXT,
    correct     INTEGER NOT NULL,
    hints       INTEGER NOT NULL DEFAULT 0,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (attempt, item, skill)
);
CREATE INDEX IF NOT EXISTS evidence_by_user ON evidence (user_sub, skill, recorded_at);
CREATE INDEX IF NOT EXISTS evidence_by_skill ON evidence (skill, user_sub);
"""


@dataclass(frozen=True)
class Evidence:
    """One graded answer, as mastery sees it.

    `attempt` is the attempt store's key for the quiz this answer was part of --
    already a hash, never the live session id -- and exists so a reloaded result
    page cannot record the same answer twice.
    """

    attempt: str
    user_sub: str
    skill: str
    item: str
    stage: Stage | None
    correct: bool
    hints: int
    recorded_at: datetime


class EvidenceStore:
    """Reads and writes evidence rows. One instance per app, beside `AttemptStore`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.path) as connection:
            connection.executescript(SCHEMA)

    def record(self, rows: Iterable[Evidence]) -> None:
        """Write rows, ignoring any already there. Idempotent, like `AttemptStore.record`."""
        with connect(self.path) as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO evidence
                    (attempt, user_sub, skill, item, stage, correct, hints, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row.attempt,
                        row.user_sub,
                        row.skill,
                        row.item,
                        row.stage,
                        int(row.correct),
                        row.hints,
                        row.recorded_at.astimezone(UTC).isoformat(),
                    )
                    for row in rows
                ],
            )

    def for_pupil(self, user_sub: str) -> dict[str, list[Evidence]]:
        """One pupil's evidence, by skill, oldest first."""
        with connect(self.path) as connection:
            rows = connection.execute(
                "SELECT * FROM evidence WHERE user_sub = ? ORDER BY recorded_at, rowid",
                (user_sub,),
            ).fetchall()
        return _by(rows, "skill")

    def for_skills(self, skills: Collection[str]) -> dict[str, dict[str, list[Evidence]]]:
        """Every pupil's evidence on these skills: pupil, then skill, oldest first."""
        if not skills:
            return {}
        marks = ",".join("?" * len(skills))
        with connect(self.path) as connection:
            rows = connection.execute(
                f"SELECT * FROM evidence WHERE skill IN ({marks}) "  # noqa: S608 -- placeholders only
                "ORDER BY recorded_at, rowid",
                tuple(skills),
            ).fetchall()
        by_pupil: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            by_pupil[row["user_sub"]].append(row)
        return {pupil: _by(pupil_rows, "skill") for pupil, pupil_rows in by_pupil.items()}


def _by(rows: Iterable[sqlite3.Row], column: str) -> dict[str, list[Evidence]]:
    grouped: dict[str, list[Evidence]] = defaultdict(list)
    for row in rows:
        grouped[row[column]].append(_from_row(row))
    return dict(grouped)


def _from_row(row: sqlite3.Row) -> Evidence:
    return Evidence(
        attempt=row["attempt"],
        user_sub=row["user_sub"],
        skill=row["skill"],
        item=row["item"],
        stage=row["stage"],
        correct=bool(row["correct"]),
        hints=row["hints"],
        recorded_at=datetime.fromisoformat(row["recorded_at"]),
    )
