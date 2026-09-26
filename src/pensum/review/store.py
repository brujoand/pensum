"""Where one instance's content decisions are kept, and how a serving path reads them.

Per instance is the design, not an implementation detail: whether something is
live is data in the running application, set on its review page, and
`pensum.review` says why it cannot be a flag in a file every deployment shares.

Two objects, and the split matters. `ReviewStore` is the SQLite table: one row
per decided piece of content, upserted, durable. `ReviewLedger` is the snapshot
a request reads -- a dict in memory, refreshed on a timer and on every write --
because the alternative is a database round trip inside `for_goal_set`, which
runs on every page that lists anything.

The table lives in the same file as attempts. A separate database would mean a
second path to configure, a second volume to mount and a second thing to back
up, for data that is written a handful of times a week.

Nothing here touches the disk until it is first asked something. The app
module builds an app at import time, and importing a module should not create a
database file as a side effect.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# What a decision can be about. These strings are stored, so renaming one is a
# migration rather than a rename.
#
# Listening is not here on purpose: it has no content of its own. Every round is
# built from reading passages, and only from the approved ones, so approving the
# passage is approving what the listening exercise asks. A separate decision
# would be a second switch for the same words.
Kind = Literal["item", "reading", "writing", "skill", "mission"]
KINDS: tuple[Kind, ...] = ("item", "reading", "writing", "skill", "mission")

Verdict = Literal["approved", "rejected"]

# What a piece of content is, on this instance, right now.
#
# * `pending`: nobody has decided, or the decision predates fingerprints.
# * `approved`: approved, and the content is still what was approved.
# * `rejected`: rejected, and the content is still what was rejected.
# * `changed`: decided, but the content has been edited since. Withheld, and
#   back in the queue, because the decision was about something else.
#
# Only `approved` is ever served to a pupil.
State = Literal["pending", "approved", "rejected", "changed"]
STATES: tuple[State, ...] = ("pending", "approved", "rejected", "changed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_reviews (
    kind        TEXT NOT NULL,
    content_id  TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    by_sub      TEXT NOT NULL,
    by_name     TEXT NOT NULL,
    note        TEXT,
    decided_at  TEXT NOT NULL,
    fingerprint TEXT,
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
    """One human's verdict on one piece of content, as it was when they read it."""

    kind: Kind
    content_id: str
    verdict: Verdict
    by_sub: str
    by_name: str
    decided_at: datetime
    note: str | None = None
    # None only on rows written before fingerprints existed. Such a row cannot
    # say what it approved, so it approves nothing.
    fingerprint: str | None = None

    @property
    def approved(self) -> bool:
        return self.verdict == "approved"

    def state_for(self, current: str) -> State:
        """What this decision means for content whose fingerprint is `current`."""
        if self.fingerprint is None:
            return "pending"
        if self.fingerprint != current:
            return "changed"
        return "approved" if self.approved else "rejected"


def migrate(connection: sqlite3.Connection) -> None:
    """Bring an existing table up to the current shape.

    The only change so far is the fingerprint column. Rows that predate it keep
    a NULL there, which `Decision.state_for` reads as pending: an instance
    upgraded to this version serves nothing until someone approves it again,
    which is the decision made for every instance, old or new.
    """
    connection.executescript(SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(content_reviews)")}
    if "fingerprint" not in columns:
        connection.execute("ALTER TABLE content_reviews ADD COLUMN fingerprint TEXT")


class ReviewStore:
    """Reads and writes review decisions. One instance per app.

    A connection per operation, as `AttemptStore` does and for the same reasons:
    SQLite connections are cheap and FastAPI will call this from more than one
    thread.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ready = False
        self._lock = threading.Lock()

    def _prepare(self) -> None:
        with self._lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5.0)
            try:
                with connection:
                    migrate(connection)
            finally:
                connection.close()
            self._ready = True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if not self._ready:
            self._prepare()
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, decision: Decision) -> None:
        """Write a decision, replacing any earlier one for the same content."""
        self.record_many([decision])

    def record_many(self, decisions: Iterable[Decision]) -> int:
        """Write several decisions in one transaction, and say how many.

        One transaction because a bulk approval is one act: four hundred
        questions approved together become live together, or not at all.

        Replacing rather than appending: the question a serving path asks is
        "may this be shown now", and a history of changed minds would answer a
        question nobody is asking.
        """
        rows = [
            (
                d.kind,
                d.content_id,
                d.verdict,
                d.by_sub,
                d.by_name,
                d.note,
                d.decided_at.astimezone(UTC).isoformat(),
                d.fingerprint,
            )
            for d in decisions
        ]
        if not rows:
            return 0
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO content_reviews
                    (kind, content_id, verdict, by_sub, by_name, note, decided_at, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (kind, content_id) DO UPDATE SET
                    verdict     = excluded.verdict,
                    by_sub      = excluded.by_sub,
                    by_name     = excluded.by_name,
                    note        = excluded.note,
                    decided_at  = excluded.decided_at,
                    fingerprint = excluded.fingerprint
                """,
                rows,
            )
        return len(rows)

    def clear(self, kind: Kind, content_id: str) -> None:
        """Forget a decision, which makes the content pending again."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM content_reviews WHERE kind = ? AND content_id = ?",
                (kind, content_id),
            )

    def decisions(self) -> dict[tuple[str, str], Decision]:
        """Every decision, keyed by what it is about.

        The whole table at once, because it is small by construction -- one row
        per authored question, template, passage, prompt, skill and mission.
        """
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT kind, content_id, verdict, by_sub, by_name, note, decided_at,"
                " fingerprint FROM content_reviews"
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
        fingerprint=row["fingerprint"],
    )


class ReviewLedger:
    """The decisions a serving path consults, cached in memory.

    Held by each content library and asked one question: given this content as
    it is now, may it be served? Nothing else in a library knows a database
    exists.
    """

    def __init__(self, store: ReviewStore, *, refresh_seconds: float = REFRESH_SECONDS) -> None:
        self._store = store
        self._refresh_seconds = refresh_seconds
        self._decisions: dict[tuple[str, str], Decision] = {}
        # Never loaded yet: the first question reads the table.
        self._loaded_at: float | None = None

    @property
    def store(self) -> ReviewStore:
        return self._store

    def reload(self) -> None:
        """Re-read the table now. Called after every write in this process."""
        self._decisions = self._store.decisions()
        self._loaded_at = time.monotonic()

    def _fresh(self) -> dict[tuple[str, str], Decision]:
        if self._loaded_at is None or time.monotonic() - self._loaded_at >= self._refresh_seconds:
            self.reload()
        return self._decisions

    def decision(self, kind: Kind, content_id: str) -> Decision | None:
        return self._fresh().get((kind, content_id))

    def decisions(self) -> dict[tuple[str, str], Decision]:
        return dict(self._fresh())

    def state(self, kind: Kind, content_id: str, fingerprint: str) -> State:
        """Where this content stands, given what it is now."""
        decision = self.decision(kind, content_id)
        if decision is None:
            return "pending"
        return decision.state_for(fingerprint)

    def publishes(self, kind: Kind, content_id: str, fingerprint: str) -> bool:
        """Whether this content may be shown to a pupil *here*.

        Only an approval of exactly this content does it. No decision, a
        rejection, and an approval of an earlier version all withhold -- the
        last because nobody has read what the file says now.
        """
        return self.state(kind, content_id, fingerprint) == "approved"
