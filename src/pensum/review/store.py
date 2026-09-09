"""Where review decisions are kept, and how a serving path reads them.

Two objects, and the split matters. `ReviewStore` is the SQLite table: one row
per decided piece of content, upserted, durable. `ReviewLedger` is the snapshot
a request reads -- a dict in memory, refreshed on a timer and on every write --
because the alternative is a database round trip inside `for_goal_set`, which
runs on every page that lists anything.

The table lives in the same file as attempts. A separate database would mean a
second path to configure, a second volume to mount and a second thing to back
up, for data that is written a handful of times a week.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# What a decision can be about. These strings are stored, so renaming one is a
# migration rather than a rename.
Kind = Literal["item", "reading", "writing"]
KINDS: tuple[Kind, ...] = ("item", "reading", "writing")

Verdict = Literal["approved", "rejected"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_reviews (
    kind        TEXT NOT NULL,
    content_id  TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    by_sub      TEXT NOT NULL,
    by_name     TEXT NOT NULL,
    note        TEXT,
    decided_at  TEXT NOT NULL,
    PRIMARY KEY (kind, content_id)
);
"""

# How long a ledger snapshot may be trusted before it is read again. A decision
# made in this process refreshes the snapshot immediately, so this only bounds
# how stale a second process can be -- which is the case that exists when the
# deployment runs more than one worker.
REFRESH_SECONDS = 30.0


@dataclass(frozen=True)
class Decision:
    """One human's verdict on one piece of content."""

    kind: Kind
    content_id: str
    verdict: Verdict
    by_sub: str
    by_name: str
    decided_at: datetime
    note: str | None = None

    @property
    def approved(self) -> bool:
        return self.verdict == "approved"


class ReviewStore:
    """Reads and writes review decisions. One instance per app.

    A connection per operation, as `AttemptStore` does and for the same reasons:
    SQLite connections are cheap and FastAPI will call this from more than one
    thread.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, decision: Decision) -> None:
        """Write a decision, replacing any earlier one for the same content.

        Replacing rather than appending: the question a serving path asks is
        "may this be shown now", and a history of changed minds would answer a
        question nobody is asking. Undoing an approval is recording a rejection,
        which is one row either way.
        """
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO content_reviews
                    (kind, content_id, verdict, by_sub, by_name, note, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (kind, content_id) DO UPDATE SET
                    verdict    = excluded.verdict,
                    by_sub     = excluded.by_sub,
                    by_name    = excluded.by_name,
                    note       = excluded.note,
                    decided_at = excluded.decided_at
                """,
                (
                    decision.kind,
                    decision.content_id,
                    decision.verdict,
                    decision.by_sub,
                    decision.by_name,
                    decision.note,
                    decision.decided_at.astimezone(UTC).isoformat(),
                ),
            )

    def clear(self, kind: Kind, content_id: str) -> None:
        """Forget a decision, so the file's own flag decides again."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM content_reviews WHERE kind = ? AND content_id = ?",
                (kind, content_id),
            )

    def decisions(self) -> dict[tuple[str, str], Decision]:
        """Every decision, keyed by what it is about.

        The whole table at once, because it is small by construction -- one row
        per authored question, passage and prompt, and the repository holds a
        few thousand of those at most.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT kind, content_id, verdict, by_sub, by_name, note, decided_at"
                " FROM content_reviews"
            ).fetchall()
        return {(row["kind"], row["content_id"]): _decision_from_row(row) for row in rows}


def _decision_from_row(row: sqlite3.Row) -> Decision:
    return Decision(
        kind=row["kind"],
        content_id=row["content_id"],
        verdict=row["verdict"],
        by_sub=row["by_sub"],
        by_name=row["by_name"],
        note=row["note"],
        decided_at=datetime.fromisoformat(row["decided_at"]),
    )


class ReviewLedger:
    """The decisions a serving path consults, cached in memory.

    Held by each content library and asked one question: given what the file
    says, may this be served? Nothing else in the library knows a database
    exists.
    """

    def __init__(self, store: ReviewStore, *, refresh_seconds: float = REFRESH_SECONDS) -> None:
        self._store = store
        self._refresh_seconds = refresh_seconds
        self._decisions: dict[tuple[str, str], Decision] = {}
        self._loaded_at = 0.0
        self.reload()

    def reload(self) -> None:
        """Re-read the table now. Called after every write in this process."""
        self._decisions = self._store.decisions()
        self._loaded_at = time.monotonic()

    def _fresh(self) -> dict[tuple[str, str], Decision]:
        if time.monotonic() - self._loaded_at >= self._refresh_seconds:
            self.reload()
        return self._decisions

    def decision(self, kind: Kind, content_id: str) -> Decision | None:
        return self._fresh().get((kind, content_id))

    def decisions(self) -> dict[tuple[str, str], Decision]:
        return dict(self._fresh())

    def publishes(self, kind: Kind, content_id: str, file_reviewed: bool) -> bool:
        """Whether this content may be shown to a pupil.

        A recorded decision wins in both directions. Approving publishes a draft
        without a release; rejecting withdraws something whose file still says
        `reviewed: true`, which is the half that makes this usable in an
        emergency -- a passage can be taken down from the site by the person who
        noticed, rather than by whoever can cut a build.

        With no row, the file decides, which is what every instance without a
        database does for everything.
        """
        decision = self.decision(kind, content_id)
        if decision is None:
            return file_reviewed
        return decision.approved
