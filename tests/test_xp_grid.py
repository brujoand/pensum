"""XP on the class grid: per pupil, in the subject, this week and in all."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from test_admin import ADMIN, ORIGIN, PUPIL, build, settings_with, sign_in, take_quiz

from pensum.scores.xp import Award, Tally, XpStore, week_start

GRID = "/nb/admin/klasse/MAT01-06"


def test_the_week_starts_on_monday_at_midnight_utc() -> None:
    sunday = datetime(2026, 10, 4, 22, 30, tzinfo=UTC)
    monday = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)

    assert week_start(sunday) == datetime(2026, 9, 28, tzinfo=UTC)
    assert week_start(monday) == monday
    assert week_start(monday + timedelta(days=6, hours=23)) == monday


def test_a_subject_tally_splits_this_week_from_the_rest(tmp_path: Path) -> None:
    store = XpStore(tmp_path / "pensum.db")
    monday = datetime(2026, 10, 5, tzinfo=UTC)

    def award(ref: str, amount: int, at: datetime, subject: str = "MAT01-06") -> None:
        store.record(
            Award(
                user_sub="u-1",
                source="quiz",
                subject=subject,
                ref=ref,
                amount=amount,
                recorded_at=at,
            )
        )

    award("last-week", 30, monday - timedelta(minutes=1))
    award("this-week", 50, monday)
    award("other-subject", 70, monday, subject="NOR01-08")

    assert store.for_subject("MAT01-06", monday) == {"u-1": Tally(week=50, total=80)}


def test_the_grid_shows_each_pupils_xp(tmp_path: Path) -> None:
    app, admin = build(settings_with(tmp_path))
    sign_in(admin, ADMIN)
    pupil = TestClient(app, base_url=ORIGIN)
    sign_in(pupil, PUPIL)
    take_quiz(app, pupil)
    earned = app.state.xp.total("u-1")

    page = admin.get(GRID).text

    assert "XP denne uka" in page
    cells = re.findall(r'<td class="class-xp">(\d+)</td>', page)
    assert cells[:2] == [str(earned), str(earned)]


def test_without_a_ledger_there_are_no_xp_columns(tmp_path: Path) -> None:
    app, admin = build(settings_with(tmp_path))
    sign_in(admin, ADMIN)
    pupil = TestClient(app, base_url=ORIGIN)
    sign_in(pupil, PUPIL)
    take_quiz(app, pupil)
    app.state.xp = None

    assert "XP denne uka" not in admin.get(GRID).text
