"""Which year (trinn) a signed-in pupil is in, asked once at their first sign-in.

The provider says who a pupil is, not which year they are in, so Pensum asks.
The answer is stored with the school year it was given in, and the current
year is computed from it: a pupil who said 4 in October 2026 is in 5 from
1 August 2027, without being asked again. Past 10 it stays at 10, the last year
of grunnskole.

One row per pupil, in the same file as the attempts. Saying it again replaces
the row, which is how a pupil who picked the wrong year corrects it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from pensum.domain.grades import FIRST_GRADE, LAST_GRADE
from pensum.scores.store import connect

# The Norwegian school year starts in August. Pupils move up over the summer,
# so the first of the month is the boundary.
SCHOOL_YEAR_STARTS = (8, 1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pupil_year (
    user_sub    TEXT PRIMARY KEY,
    grade       INTEGER NOT NULL,
    school_year INTEGER NOT NULL,
    recorded_at TEXT NOT NULL
);
-- The Arkade timer, on unless the pupil switched it off (docs/design/arkade.md,
-- rule 2). A table of its own so an existing database gains it on start.
CREATE TABLE IF NOT EXISTS arkade_timer (
    user_sub TEXT PRIMARY KEY,
    timer_on INTEGER NOT NULL
);
"""


def school_year(day: date) -> int:
    """The calendar year a school year started in: 2026 for anything from 1 August 2026."""
    return day.year if (day.month, day.day) >= SCHOOL_YEAR_STARTS else day.year - 1


class ProfileStore:
    """Reads and writes each pupil's year. One instance per app, beside `XpStore`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.path) as connection:
            connection.executescript(SCHEMA)

    def set_grade(self, user_sub: str, grade: int, now: datetime) -> None:
        """Record that this pupil is in `grade` now, replacing what they said before."""
        if not FIRST_GRADE <= grade <= LAST_GRADE:
            raise ValueError(f"grade {grade} is outside grunnskole")
        with connect(self.path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO pupil_year (user_sub, grade, school_year, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_sub,
                    grade,
                    school_year(now.astimezone(UTC).date()),
                    now.astimezone(UTC).isoformat(),
                ),
            )

    def grade(self, user_sub: str, now: datetime) -> int | None:
        """The year this pupil is in now, or None if they have not said."""
        with connect(self.path) as connection:
            row = connection.execute(
                "SELECT grade, school_year FROM pupil_year WHERE user_sub = ?", (user_sub,)
            ).fetchone()
        if row is None:
            return None
        moved_up = school_year(now.astimezone(UTC).date()) - row["school_year"]
        return min(row["grade"] + max(moved_up, 0), LAST_GRADE)

    def timer_on(self, user_sub: str) -> bool:
        """Whether Arkade games are timed for this pupil. On until they say otherwise."""
        with connect(self.path) as connection:
            row = connection.execute(
                "SELECT timer_on FROM arkade_timer WHERE user_sub = ?", (user_sub,)
            ).fetchone()
        return True if row is None else bool(row["timer_on"])

    def set_timer(self, user_sub: str, on: bool) -> None:
        with connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO arkade_timer (user_sub, timer_on) VALUES (?, ?)",
                (user_sub, int(on)),
            )
