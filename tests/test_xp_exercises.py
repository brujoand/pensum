"""XP for reading aloud, writing and listening: earned when marked, by the rules in xp.md."""

from __future__ import annotations

from pathlib import Path

from test_admin import PUPIL, build, settings_with, sign_in
from test_listening import words_on
from test_writing import real_attempt

from pensum.config import Settings
from pensum.scores.xp import PER_CORRECT, PER_FINISH

READING = "/nb/klasse/2/NOR01-08/lesing"
WRITING = "/nb/klasse/1/NOR01-08/skriving/nor-kv1107-sma-streker/spor"
LISTENING = "/nb/klasse/1/NOR01-08/lytting"


def signed_in(tmp_path: Path):
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)
    return app, client


def a_passage(app) -> str:
    return app.state.reading.for_goal_set("KV1107")[0].id


def test_finishing_a_reading_earns_xp_and_says_so(tmp_path: Path) -> None:
    app, client = signed_in(tmp_path)

    page = client.post(f"{READING}/{a_passage(app)}/tid", data={"seconds": "60"}).text

    assert app.state.xp.total("u-1") == PER_FINISH
    assert f"+{PER_FINISH} XP" in page


def test_reading_the_same_passage_again_earns_again(tmp_path: Path) -> None:
    app, client = signed_in(tmp_path)
    url = f"{READING}/{a_passage(app)}/tid"

    client.post(url, data={"seconds": "60"})
    client.post(url, data={"seconds": "60"})

    assert app.state.xp.total("u-1") == 2 * PER_FINISH


def test_finishing_a_tracing_earns_xp(tmp_path: Path) -> None:
    app, client = signed_in(tmp_path)

    page = client.post(WRITING, json=real_attempt(client, WRITING, "iltj")).text

    assert app.state.xp.total("u-1") == PER_FINISH
    assert f"+{PER_FINISH} XP" in page


def test_a_tracing_left_half_done_earns_nothing(tmp_path: Path) -> None:
    app, client = signed_in(tmp_path)

    client.post(WRITING, json=real_attempt(client, WRITING, "il"))

    assert app.state.xp.total("u-1") == 0


def test_each_right_spelling_earns_xp(tmp_path: Path) -> None:
    app, client = signed_in(tmp_path)
    words = words_on(client, LISTENING)
    given = [*words[:-1], "feil"]

    page = client.post(f"{LISTENING}/svar", json={"given": given}).text

    expected = PER_CORRECT * (len(words) - 1)
    assert app.state.xp.total("u-1") == expected
    assert f"+{expected} XP" in page


def test_no_ledger_means_nothing_is_said(tmp_path: Path) -> None:
    app, client = build(Settings(database_path=tmp_path / "pensum.db"))

    page = client.post(f"{READING}/{a_passage(app)}/tid", data={"seconds": "60"}).text

    assert app.state.xp is None
    assert " XP" not in page
