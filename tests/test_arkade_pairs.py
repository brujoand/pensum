"""Memory pairs: a board from start to result."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_admin import ADMIN, PUPIL, build, settings_with, sign_in

from pensum.config import Settings
from pensum.scores.xp import PER_CORRECT, PER_FINISH


def board_of(page: str) -> dict:
    found = re.search(r'<script type="application/json" id="pairs-round">(.*?)</script>', page)
    assert found, "no board on the page"
    return json.loads(found.group(1))


@pytest.fixture
def pupil(tmp_path: Path):
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)
    return app, client


def test_the_hub_offers_memory(pupil) -> None:
    _, client = pupil

    assert 'href="/nb/arkade/par/matte"' in client.get("/nb/arkade").text


def test_a_board_is_six_pairs_in_twelve_cards(pupil) -> None:
    _, client = pupil

    board = board_of(client.get("/nb/arkade/par/matte").text)

    assert board["timed"] is True
    assert len(board["answers"]) == 6
    assert len(board["cards"]) == 12
    for pair in range(6):
        assert sum(1 for card in board["cards"] if card["pair"] == pair) == 2


def test_a_cleared_board_earns_xp_and_no_evidence(pupil) -> None:
    app, client = pupil
    board = board_of(client.get("/nb/arkade/par/matte").text)

    page = client.post(f"/nb/arkade/runde/{board['round']}", json={"picks": [0] * 6}).text

    assert "6 av 6 riktige" in page
    assert 'href="/nb/arkade/par/matte"' in page
    assert app.state.xp.total("u-1") == 6 * PER_CORRECT + PER_FINISH
    assert app.state.evidence.for_pupil("u-1") == {}


def test_pairs_left_when_time_ran_out_earn_nothing(pupil) -> None:
    app, client = pupil
    board = board_of(client.get("/nb/arkade/par/matte").text)

    page = client.post(
        f"/nb/arkade/runde/{board['round']}", json={"picks": [0, 0, None, None, None, None]}
    ).text

    assert "2 av 6 riktige" in page
    assert app.state.xp.total("u-1") == 2 * PER_CORRECT + PER_FINISH


def test_the_timer_setting_reaches_the_board(pupil) -> None:
    _, client = pupil
    client.post("/nb/arkade/tidtaker", data={"timer": "av"})

    assert board_of(client.get("/nb/arkade/par/matte").text)["timed"] is False


def test_an_unknown_memory_game_is_a_404(pupil) -> None:
    _, client = pupil

    assert client.get("/nb/arkade/par/norsk").status_code == 404


def test_balloons_still_come_back_to_balloons(pupil) -> None:
    _, client = pupil
    page = client.get("/nb/arkade/ballonger/matte").text
    found = re.search(r'id="balloons-round">(.*?)</script>', page)
    assert found
    played = json.loads(found.group(1))

    result = client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": []}).text

    assert 'href="/nb/arkade/ballonger/matte"' in result


def test_without_sign_in_the_year_rides_in_the_address() -> None:
    _, client = build(Settings())

    board = board_of(client.get("/nb/arkade/par/matte?trinn=2").text)
    page = client.post(f"/nb/arkade/runde/{board['round']}?trinn=2", json={"picks": [0] * 6}).text

    assert 'href="/nb/arkade/par/matte?trinn=2"' in page


def test_an_administrator_who_picked_a_year_on_the_hub_reaches_the_board(tmp_path: Path) -> None:
    """As for balloons: the hub's year rides along, or the board sends them back."""
    _, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN, year=None)

    hub = client.get("/nb/arkade?trinn=4").text
    link = re.search(r'href="(/nb/arkade/par/matte[^"]*)"', hub)
    assert link
    board = client.get(link.group(1).replace("&amp;", "&"), follow_redirects=False)

    assert board.status_code == 200
    assert len(board_of(board.text)["cards"]) == 12


def test_a_face_down_card_does_not_draw_its_text() -> None:
    """The back hides the face only where the browser hides the side facing
    away. Where it does not, a board would start with every answer showing."""
    import pensum.web

    css = (Path(pensum.web.__file__).parent / "static" / "pensum.css").read_text()
    down = re.search(r"\n\.pair-card__face \{(.*?)\}", css, re.DOTALL)
    up = re.search(r"\n\.pair-card--up \.pair-card__face \{(.*?)\}", css, re.DOTALL)

    assert down and "visibility: hidden" in down.group(1)
    assert up and "visibility: visible" in up.group(1)
