"""XP: points a signed-in pupil earns for right answers and finished runs.

The rules are `docs/design/xp.md`, and they are fixed: 10 for each correct
answer, 20 for finishing. Hints, time and wrong answers change nothing, and XP
is never taken away. An answer on a sensitive skill earns nothing, and a run
made only of those earns nothing for finishing either.

Stored as a ledger, one row per thing that earned it, in the same file as the
attempts and the evidence. A total is always the sum of the rows. The key is
(pupil, source, ref), and `ref` is the attempt hash for a quiz or a nivåtest,
so a reloaded result page writes the same row again and is ignored.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pensum.scores.store import connect

PER_CORRECT = 10
PER_FINISH = 20

Source = Literal["quiz", "placement", "reading", "writing", "listening", "arkade"]

# Created on open, like `attempts` and `evidence`; an existing database gains
# it on the next start.
SCHEMA = """
CREATE TABLE IF NOT EXISTS xp (
    user_sub    TEXT NOT NULL,
    source      TEXT NOT NULL,
    subject     TEXT NOT NULL,
    ref         TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (user_sub, source, ref)
);
CREATE INDEX IF NOT EXISTS xp_by_subject ON xp (subject, user_sub);
"""


def for_run(answers: Iterable[tuple[bool, bool]]) -> int:
    """XP for a finished run, from (correct, sensitive) per answer."""
    counted = [correct for correct, sensitive in answers if not sensitive]
    if not counted:
        return 0
    return PER_CORRECT * sum(counted) + PER_FINISH


def week_start(now: datetime) -> datetime:
    """Monday 00:00 UTC of the week `now` is in. UTC, like the mastery rules' days."""
    today = now.astimezone(UTC).date()
    day = today - timedelta(days=today.weekday())
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


@dataclass(frozen=True)
class Tally:
    """One pupil's XP in one subject, for the class grid."""

    week: int = 0
    total: int = 0


@dataclass(frozen=True)
class Award:
    """One ledger row."""

    user_sub: str
    source: Source
    subject: str
    ref: str
    amount: int
    recorded_at: datetime


class XpStore:
    """Reads and writes the XP ledger. One instance per app, beside `EvidenceStore`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.path) as connection:
            connection.executescript(SCHEMA)

    def record(self, award: Award) -> None:
        """Write an award, ignoring it if this pupil already has one for `ref`.

        A zero award is not written: it would say something was earned.
        """
        if award.amount <= 0:
            return
        with connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO xp (user_sub, source, subject, ref, amount, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    award.user_sub,
                    award.source,
                    award.subject,
                    award.ref,
                    award.amount,
                    award.recorded_at.astimezone(UTC).isoformat(),
                ),
            )

    def for_subject(self, subject: str, since: datetime) -> dict[str, Tally]:
        """Every pupil's XP in `subject`: earned since `since`, and in all."""
        with connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT user_sub,
                       SUM(CASE WHEN recorded_at >= ? THEN amount ELSE 0 END) AS week,
                       SUM(amount) AS total
                FROM xp WHERE subject = ? GROUP BY user_sub
                """,
                (since.astimezone(UTC).isoformat(), subject),
            ).fetchall()
        return {row["user_sub"]: Tally(week=row["week"], total=row["total"]) for row in rows}

    def total(self, user_sub: str) -> int:
        """Everything this pupil has earned, in every subject."""
        with connect(self.path) as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM xp WHERE user_sub = ?", (user_sub,)
            ).fetchone()
        return int(row[0])
