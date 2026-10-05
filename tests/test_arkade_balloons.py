"""Arkade: the hub, the timer setting, and a balloon round from start to result."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_admin import ADMIN, PUPIL, build, settings_with, sign_in

from pensum.arkade.items import Item
from pensum.arkade.rounds import ROUND_LIFETIME, RoundStore, mark
from pensum.auth.models import User
from pensum.config import Settings
from pensum.scores.profile import ProfileStore
from pensum.scores.xp import PER_CORRECT, PER_FINISH

OTHER = User(sub="u-2", name="Kari", groups=("pupils",))
NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)


def item(n: int) -> Item:
    return Item(
        id=f"i{n}",
        rule="false_statement",
        candidates=("a", "b"),
        matches=frozenset({1}),
        answer="b",
    )


def round_of(page: str) -> dict:
    found = re.search(r'<script type="application/json" id="balloons-round">(.*?)</script>', page)
    assert found, "no round on the page"
    return json.loads(found.group(1))


def right_picks(played: dict) -> list[int]:
    return [entry["matches"][0] for entry in played["items"]]


# --- the timer setting -----------------------------------------------------


def test_the_timer_is_on_until_the_pupil_switches_it_off(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "p.db")
    assert store.timer_on("u-1")

    store.set_timer("u-1", False)
    assert not store.timer_on("u-1")

    store.set_timer("u-1", True)
    assert store.timer_on("u-1")


# --- rounds and marking ----------------------------------------------------


def test_no_pick_is_neither_right_nor_wrong() -> None:
    played = RoundStore().create(
        "matte", "MAT01-06", [item(1), item(2), item(3)], timed=True, now=NOW, user_sub="u-1"
    )

    outcomes = [m.correct for m in mark(played, [1, 0, None])]

    assert outcomes == [True, False, None]


def test_a_short_list_of_picks_leaves_the_rest_unanswered() -> None:
    played = RoundStore().create(
        "matte", "MAT01-06", [item(1), item(2)], timed=False, now=NOW, user_sub="u-1"
    )

    assert [m.correct for m in mark(played, [1])] == [True, None]


def test_a_round_is_finished_once_and_only_by_its_pupil() -> None:
    store = RoundStore()
    played = store.create("matte", "MAT01-06", [item(1)], timed=True, now=NOW, user_sub="u-1")

    assert store.finish(played.id, "u-2", NOW) is None
    assert store.finish(played.id, "u-1", NOW) == played
    assert store.finish(played.id, "u-1", NOW) is None


def test_an_old_round_is_swept() -> None:
    store = RoundStore()
    played = store.create("matte", "MAT01-06", [item(1)], timed=True, now=NOW, user_sub=None)

    later = NOW + ROUND_LIFETIME + timedelta(seconds=1)

    assert store.finish(played.id, None, later) is None
    assert len(store) == 0


# --- the pages, signed in --------------------------------------------------


@pytest.fixture
def pupil(tmp_path: Path):
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)
    return app, client


def test_the_hub_offers_the_three_balloon_games(pupil) -> None:
    _, client = pupil

    page = client.get("/nb/arkade").text

    for game in ("matte", "norsk", "engelsk"):
        assert f'href="/nb/arkade/ballonger/{game}"' in page
    assert "8 ballonger per runde" in page


def test_the_home_page_links_to_arkade(pupil) -> None:
    _, client = pupil

    assert 'href="/nb/arkade"' in client.get("/nb/").text


def test_a_math_round_is_eight_timed_items_for_the_pupils_year(pupil) -> None:
    _, client = pupil

    played = round_of(client.get("/nb/arkade/ballonger/matte").text)

    assert played["timed"] is True
    assert len(played["items"]) == 8
    assert all(entry["rule"] == "false_statement" for entry in played["items"])
    # Year 4: tables and division, never plain adding.
    assert all(("·" in e["answer"]) or (":" in e["answer"]) for e in played["items"])


def test_switching_the_timer_off_untimes_the_next_round(pupil) -> None:
    app, client = pupil

    response = client.post("/nb/arkade/tidtaker", data={"timer": "av"}, follow_redirects=False)

    assert response.headers["location"] == "/nb/arkade"
    assert not app.state.profiles.timer_on("u-1")
    assert round_of(client.get("/nb/arkade/ballonger/matte").text)["timed"] is False


def test_a_perfect_round_earns_xp_and_evidence(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/ballonger/matte").text)

    page = client.post(
        f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)}
    ).text

    assert "8 av 8 riktige" in page
    assert app.state.xp.total("u-1") == 8 * PER_CORRECT + PER_FINISH
    rows = [row for rows in app.state.evidence.for_pupil("u-1").values() for row in rows]
    assert len(rows) == 8
    assert all(row.correct for row in rows)


def test_time_running_out_is_not_evidence(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/ballonger/matte").text)

    page = client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": [None] * 8}).text

    assert "0 av 8 riktige" in page
    assert app.state.evidence.for_pupil("u-1") == {}
    assert app.state.xp.total("u-1") == PER_FINISH


def test_a_round_cannot_be_finished_twice(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/ballonger/matte").text)
    url = f"/nb/arkade/runde/{played['round']}"

    client.post(url, json={"picks": right_picks(played)})
    again = client.post(url, json={"picks": right_picks(played)})

    assert again.status_code == 404
    assert app.state.xp.total("u-1") == 8 * PER_CORRECT + PER_FINISH


def test_another_pupil_cannot_finish_the_round(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)
    played = round_of(client.get("/nb/arkade/ballonger/matte").text)

    sign_in(client, OTHER, year=4)
    response = client.post(
        f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)}
    )

    assert response.status_code == 404
    assert app.state.xp.total("u-2") == 0


def test_a_spelling_round_speaks_each_word(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=2)

    played = round_of(client.get("/nb/arkade/ballonger/norsk").text)

    assert len(played["items"]) == 8
    for entry in played["items"]:
        assert entry["rule"] == "spoken_word"
        assert entry["spoken"] == entry["answer"] == entry["candidates"][entry["matches"][0]]


def test_an_unknown_game_is_a_404(pupil) -> None:
    _, client = pupil

    assert client.get("/nb/arkade/ballonger/sjakk").status_code == 404


def test_an_administrator_with_no_year_picks_one_on_the_hub(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN, year=None)

    page = client.get("/nb/arkade").text

    assert 'href="/nb/arkade?trinn=3"' in page


def test_a_signed_out_visitor_is_sent_to_sign_in(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))

    response = client.get("/nb/arkade", follow_redirects=False)

    assert response.headers["location"] == "/auth/login?next=/nb/arkade"


# --- without sign-in -------------------------------------------------------


def test_without_sign_in_the_year_and_timer_ride_in_the_address() -> None:
    _, client = build(Settings())

    hub = client.get("/nb/arkade?trinn=3").text
    assert 'href="/nb/arkade/ballonger/matte?trinn=3"' in hub

    played = round_of(client.get("/nb/arkade/ballonger/matte?trinn=3&tidtaker=av").text)
    assert played["timed"] is False

    page = client.post(
        f"/nb/arkade/runde/{played['round']}?trinn=3&tidtaker=av",
        json={"picks": right_picks(played)},
    ).text
    assert "8 av 8 riktige" in page
    assert 'href="/nb/arkade/ballonger/matte?trinn=3&amp;tidtaker=av"' in page
