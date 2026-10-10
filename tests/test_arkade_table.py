"""Gangetabellen: the table, and a round from start to result."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from urllib.parse import parse_qs, urlsplit

import pytest
from test_admin import PUPIL, build, settings_with, sign_in

from pensum.arkade.rounds import Marked
from pensum.arkade.table import (
    CELLS,
    KNOWN,
    NOT_YET,
    SKILL,
    UNASKED,
    Table,
    cell_of,
    from_evidence,
    from_text,
    item_for,
)
from pensum.config import Settings
from pensum.scores.evidence import Evidence
from pensum.scores.xp import PER_CORRECT, PER_FINISH
from pensum.skills.loader import SkillLibrary
from pensum.web.arkade_routes import MAX_PICKS, TABLE_ROUND

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


def rng(seed: int) -> Random:
    return Random(seed)  # noqa: S311 -- reproducible rounds, not cryptography


def round_of(page: str) -> dict:
    found = re.search(r'<script type="application/json" id="times-round">(.*?)</script>', page)
    assert found, "no round on the page"
    return json.loads(found.group(1))


def right_picks(played: dict) -> list[int]:
    return [entry["value"] for entry in played["items"]]


def cells_asked(played: dict) -> set[tuple[int, int]]:
    return {tuple(int(n) for n in entry["cell"].split("-")) for entry in played["items"]}


def classes(page: str, state: str) -> int:
    return len(re.findall(rf'class="times-cell times-cell--{state}"', page))


def carried(url: str) -> Table:
    return from_text(parse_qs(urlsplit(url).query).get("tabell", [""])[0])


def link(page: str, to: str) -> str:
    found = re.search(rf'href="({re.escape(to)}[^"]*)"', page)
    assert found, f"no link to {to}"
    return found.group(1).replace("&amp;", "&")


def row(cell: tuple[int, int], *, correct: bool, at: datetime) -> Evidence:
    return Evidence(
        attempt=f"a-{at.isoformat()}",
        user_sub="u-1",
        skill=SKILL or "",
        item=item_for(cell).id,
        stage=None,
        correct=correct,
        hints=0,
        recorded_at=at,
    )


# --- the table ----------------------------------------------------------------


def test_the_table_is_a_hundred_cells() -> None:
    assert len(CELLS) == len(set(CELLS)) == 100
    assert CELLS[0] == (1, 1)
    assert CELLS[-1] == (10, 10)


def test_a_cell_is_a_product_to_type() -> None:
    item = item_for((7, 8))

    assert item.id == "gange:7·8"
    assert item.shown == "7 · 8"
    assert item.answer == "7 · 8 = 56"
    assert item.is_match(56)
    assert not item.is_match(54)
    # A number no product reaches is wrong, not an error.
    assert not item.is_match(999)
    assert Marked(item, True, 56).scores


def test_seven_times_eight_is_not_eight_times_seven() -> None:
    assert item_for((7, 8)).id != item_for((8, 7)).id


def test_an_item_names_its_cell_and_any_other_item_names_none() -> None:
    assert all(cell_of(item_for(cell).id) == cell for cell in CELLS)
    assert cell_of("mat:7·8") is None
    assert cell_of("gange:11·2") is None
    assert cell_of("gange:7") is None
    assert cell_of("gange:x·y") is None


def test_the_skill_exists() -> None:
    assert SKILL in {s.id for s in SkillLibrary.load().for_subject("MAT01-06").skills}


def test_an_empty_table_has_asked_nothing() -> None:
    empty = Table({})

    assert empty.count(UNASKED) == 100
    assert empty.count(KNOWN) == empty.count(NOT_YET) == 0
    assert len(empty.rows()) == 10
    assert empty.rows()[6][7] == {"a": 7, "b": 8, "value": 56, "state": "unasked"}


def test_a_table_survives_the_address() -> None:
    known = Table({(7, 8): KNOWN, (10, 10): NOT_YET})

    assert len(known.text) == 100
    assert from_text(known.text) == known


@pytest.mark.parametrize("text", ["", "1", "0" * 99, "0" * 101, "3" + "0" * 99, "x" * 100])
def test_what_is_not_a_table_is_an_empty_one(text: str) -> None:
    assert from_text(text) == Table({})


def test_an_answer_colours_its_cell_and_no_answer_leaves_it() -> None:
    before = Table({(2, 2): KNOWN})
    after = before.after(
        [
            Marked(item_for((7, 8)), True, 56),
            Marked(item_for((6, 7)), False, 43),
            Marked(item_for((9, 9)), None),
            Marked(item_for((2, 2)), None),
        ]
    )

    assert after.state((7, 8)) == KNOWN
    assert after.state((6, 7)) == NOT_YET
    assert after.state((9, 9)) == UNASKED
    assert after.state((2, 2)) == KNOWN
    assert before.state((7, 8)) == UNASKED


def test_the_latest_answer_is_the_one_that_counts() -> None:
    hour = timedelta(hours=1)
    rows = [
        row((7, 8), correct=True, at=NOW + hour),
        row((7, 8), correct=False, at=NOW),
        row((3, 3), correct=True, at=NOW),
        row((3, 3), correct=False, at=NOW + hour),
    ]

    known = from_evidence(rows)

    assert known.state((7, 8)) == KNOWN
    assert known.state((3, 3)) == NOT_YET
    assert known.count(UNASKED) == 98


def test_a_balloon_about_the_same_product_does_not_colour_the_table() -> None:
    balloon = Evidence("a", "u-1", SKILL or "", "mat:7·8", None, True, 0, NOW)

    assert from_evidence([balloon]) == Table({})


# --- which cells a round asks for ------------------------------------------------


def test_every_cell_is_asked_once_before_any_is_asked_again() -> None:
    known = Table({})
    asked: list[tuple[int, int]] = []
    for seed in range(10):
        items = known.questions(rng(seed), 10)
        assert len(items) == 10
        known = known.after(Marked(item, True, 0) for item in items)
        asked += [cell_of(item.id) for item in items]

    assert sorted(asked) == sorted(CELLS)


def test_the_cells_come_in_no_order() -> None:
    first = [cell_of(item.id) for item in Table({}).questions(rng(1), 10)]

    assert first != list(CELLS[:10])
    assert first != [cell_of(item.id) for item in Table({}).questions(rng(2), 10)]


def test_a_round_is_topped_up_with_what_is_not_known_yet_then_what_is() -> None:
    asked = dict.fromkeys(CELLS, KNOWN)
    del asked[(7, 8)]
    asked[(6, 7)] = NOT_YET
    asked[(8, 8)] = NOT_YET

    cells = [cell_of(item.id) for item in Table(asked).questions(rng(3), 10)]

    assert len(cells) == len(set(cells)) == 10
    assert {(7, 8), (6, 7), (8, 8)} <= set(cells)


def test_a_drill_is_only_what_is_not_known_yet_however_few() -> None:
    known = Table({(7, 8): NOT_YET, (6, 7): NOT_YET, (2, 2): KNOWN})

    cells = {cell_of(item.id) for item in known.questions(rng(1), 10, drill=True)}

    assert cells == {(7, 8), (6, 7)}
    assert Table({(2, 2): KNOWN}).questions(rng(1), 10, drill=True) == []


def test_a_drill_is_no_longer_than_a_round() -> None:
    known = Table(dict.fromkeys(CELLS[:30], NOT_YET))

    assert len(known.questions(rng(1), 10, drill=True)) == 10


def test_a_full_round_is_within_what_the_server_will_accept() -> None:
    assert TABLE_ROUND <= MAX_PICKS


# --- a round, signed in ----------------------------------------------------------


@pytest.fixture
def pupil(tmp_path: Path):
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)
    return app, client


def test_the_hub_offers_gangetabellen(pupil) -> None:
    _, client = pupil

    assert 'href="/nb/arkade/gangetabellen"' in client.get("/nb/arkade").text


def test_a_new_pupil_sees_an_empty_table(pupil) -> None:
    _, client = pupil
    page = client.get("/nb/arkade/gangetabellen").text

    assert classes(page, "unasked") == 100
    assert "Ikke spurt ennå: 100" in page
    assert 'href="/nb/arkade/gangetabellen/runde"' in page
    # Nothing to drill yet, and nothing to say about where the table is kept.
    assert "ov=1" not in page
    assert "ikke logget inn" not in page


def test_a_round_is_ten_timed_products_with_no_lives(pupil) -> None:
    _, client = pupil

    played = round_of(client.get("/nb/arkade/gangetabellen/runde").text)

    assert played["timed"] is True
    assert "lives" not in played
    assert len(played["items"]) == TABLE_ROUND
    assert len(cells_asked(played)) == TABLE_ROUND
    for entry in played["items"]:
        a, b = (int(n) for n in entry["cell"].split("-"))
        assert entry["shown"] == f"{a} · {b}"
        assert entry["value"] == a * b
        assert entry["answer"] == f"{a} · {b} = {a * b}"


def test_the_round_page_draws_the_table_with_a_cell_for_every_product(pupil) -> None:
    _, client = pupil
    page = client.get("/nb/arkade/gangetabellen/runde").text

    assert "times-table--small" in page
    for entry in round_of(page)["items"]:
        assert f'id="times-cell-{entry["cell"]}"' in page


def test_answers_fill_the_table_and_are_evidence(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/gangetabellen/runde").text)
    picks = right_picks(played)
    picks[0] += 1
    picks[1] += 1

    result = client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": picks}).text

    assert "8 av 10 riktige" in result
    assert 'href="/nb/arkade/gangetabellen"' in result
    assert app.state.xp.total("u-1") == 8 * PER_CORRECT + PER_FINISH
    assert len(app.state.evidence.for_pupil("u-1")[SKILL]) == 10

    page = client.get("/nb/arkade/gangetabellen").text
    assert classes(page, "known") == 8
    assert classes(page, "not_yet") == 2
    assert classes(page, "unasked") == 90
    assert "Kan: 8" in page
    assert "Øv på de 2 du ikke kan ennå" in page
    assert 'href="/nb/arkade/gangetabellen/runde?ov=1"' in page


def test_the_next_round_asks_for_other_cells(pupil) -> None:
    _, client = pupil
    first = round_of(client.get("/nb/arkade/gangetabellen/runde").text)
    client.post(f"/nb/arkade/runde/{first['round']}", json={"picks": right_picks(first)})

    second = round_of(client.get("/nb/arkade/gangetabellen/runde").text)

    assert not cells_asked(first) & cells_asked(second)


def test_a_drill_asks_only_for_what_was_wrong_and_a_right_answer_clears_it(pupil) -> None:
    _, client = pupil
    first = round_of(client.get("/nb/arkade/gangetabellen/runde").text)
    picks = right_picks(first)
    picks[3] += 1
    client.post(f"/nb/arkade/runde/{first['round']}", json={"picks": picks})

    drill = round_of(client.get("/nb/arkade/gangetabellen/runde?ov=1").text)

    assert [entry["cell"] for entry in drill["items"]] == [first["items"][3]["cell"]]

    client.post(f"/nb/arkade/runde/{drill['round']}", json={"picks": right_picks(drill)})
    page = client.get("/nb/arkade/gangetabellen").text
    assert classes(page, "known") == 10
    assert classes(page, "not_yet") == 0


def test_a_drill_with_nothing_to_drill_goes_back_to_the_table(pupil) -> None:
    _, client = pupil

    response = client.get("/nb/arkade/gangetabellen/runde?ov=1", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/nb/arkade/gangetabellen"


def test_products_time_took_stay_unasked(pupil) -> None:
    app, client = pupil
    played = round_of(client.get("/nb/arkade/gangetabellen/runde").text)

    client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)[:4]})

    assert len(app.state.evidence.for_pupil("u-1")[SKILL]) == 4
    assert classes(client.get("/nb/arkade/gangetabellen").text, "unasked") == 96


def test_a_signed_in_pupils_table_never_rides_in_the_address(pupil) -> None:
    _, client = pupil
    played = round_of(client.get("/nb/arkade/gangetabellen/runde").text)
    result = client.post(
        f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)}
    ).text

    assert "tabell=" not in result
    assert "tabell=" not in client.get("/nb/arkade/gangetabellen").text
    assert "tabell=" not in client.get("/nb/arkade").text
    # And one put in the address by hand is not believed.
    page = client.get("/nb/arkade/gangetabellen?tabell=" + "1" * 100).text
    assert classes(page, "known") == 10


def test_another_pupils_table_is_their_own(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=4)
    played = round_of(client.get("/nb/arkade/gangetabellen/runde").text)
    client.post(f"/nb/arkade/runde/{played['round']}", json={"picks": right_picks(played)})

    other = from_evidence(app.state.evidence.for_pupil("u-2").get(SKILL, []))

    assert other == Table({})


# --- a round, with nobody signed in ------------------------------------------------


def test_without_sign_in_the_table_rides_in_the_address() -> None:
    _, client = build(Settings())
    start = client.get("/nb/arkade/gangetabellen?trinn=4").text

    assert "ikke logget inn" in start
    page = client.get(link(start, "/nb/arkade/gangetabellen/runde")).text
    played = round_of(page)
    post = re.search(r'data-post-url="([^"]+)"', page).group(1).replace("&amp;", "&")
    picks = right_picks(played)
    picks[0] += 1

    result = client.post(post, json={"picks": picks}).text

    again = link(result, "/nb/arkade/gangetabellen")
    assert "trinn=4" in again
    table = carried(again)
    assert table.count(KNOWN) == 9
    assert table.count(NOT_YET) == 1
    assert {cell for cell in CELLS if table.state(cell) != UNASKED} == cells_asked(played)

    # The table page shows it, and the next round builds on it.
    overview = client.get(again).text
    assert classes(overview, "known") == 9
    second_page = client.get(link(overview, "/nb/arkade/gangetabellen/runde")).text
    second = round_of(second_page)
    assert not cells_asked(second) & cells_asked(played)
    post = re.search(r'data-post-url="([^"]+)"', second_page).group(1).replace("&amp;", "&")
    result = client.post(post, json={"picks": right_picks(second)}).text
    assert carried(link(result, "/nb/arkade/gangetabellen")).count(KNOWN) == 19


def test_without_sign_in_the_hub_keeps_the_table_between_rounds() -> None:
    _, client = build(Settings())
    text = Table({(7, 8): KNOWN}).text

    hub = client.get(f"/nb/arkade?trinn=4&tabell={text}").text

    assert carried(link(hub, "/nb/arkade/gangetabellen")).state((7, 8)) == KNOWN
    assert f"tabell={text}" in link(hub, "/nb/arkade?trinn=4")


def test_without_sign_in_an_empty_table_adds_nothing_to_the_address() -> None:
    _, client = build(Settings())

    assert "tabell=" not in client.get("/nb/arkade?trinn=4").text
    assert "tabell=" not in client.get("/nb/arkade/gangetabellen?trinn=4").text


def test_without_sign_in_a_drill_is_what_the_address_says_is_not_known() -> None:
    _, client = build(Settings())
    text = Table({(7, 8): NOT_YET, (2, 2): KNOWN}).text

    played = round_of(client.get(f"/nb/arkade/gangetabellen/runde?ov=1&tabell={text}").text)

    assert [entry["cell"] for entry in played["items"]] == ["7-8"]


def test_the_other_games_still_come_back_with_their_address() -> None:
    _, client = build(Settings())
    page = client.get("/nb/arkade/par/matte?trinn=2").text
    board = json.loads(
        re.search(r'<script type="application/json" id="pairs-round">(.*?)</script>', page).group(1)
    )

    result = client.post(f"/nb/arkade/runde/{board['round']}?trinn=2", json={"picks": [0] * 6}).text

    assert 'href="/nb/arkade/par/matte?trinn=2"' in result
    assert 'href="/nb/arkade?trinn=2"' in result


def test_a_cell_of_the_table_has_a_height_of_its_own() -> None:
    """`aspect-ratio` does nothing on a table cell. The small table writes no
    text in its cells, so without a height they were as low as nothing and the
    table could not be read."""
    import pensum.web

    css = (Path(pensum.web.__file__).parent / "static" / "pensum.css").read_text()
    cell = re.search(r"\n\.times-cell \{(.*?)\}", css, re.DOTALL).group(1)
    small = re.search(r"\n\.times-table--small \{(.*?)\}", css, re.DOTALL).group(1)

    assert "height: var(--cell)" in cell
    assert "aspect-ratio" not in cell
    assert "--cell:" in small
    # The row and column numbers are still written beside a product.
    headers = re.search(r"\n\.times-table--small th \{(.*?)\}", css, re.DOTALL).group(1)
    assert "font-size: 0;" not in headers


# --- which years are offered the table ---------------------------------------------


@pytest.mark.parametrize("year", range(1, 8))
def test_years_one_to_seven_are_offered_the_table(year: int) -> None:
    _, client = build(Settings())

    assert (
        f'href="/nb/arkade/gangetabellen?trinn={year}"'
        in client.get(f"/nb/arkade?trinn={year}").text
    )
    assert client.get(f"/nb/arkade/gangetabellen?trinn={year}").status_code == 200
    assert (
        len(round_of(client.get(f"/nb/arkade/gangetabellen/runde?trinn={year}").text)["items"])
        == 10
    )


@pytest.mark.parametrize("year", [8, 9, 10])
def test_years_eight_to_ten_are_not(year: int) -> None:
    _, client = build(Settings())

    hub = client.get(f"/nb/arkade?trinn={year}").text
    assert "/arkade/gangetabellen" not in hub
    assert 'id="arkade-table"' not in hub
    for page in ("gangetabellen", "gangetabellen/runde"):
        response = client.get(
            f"/nb/arkade/{page}?trinn={year}&tabell={'1' * 100}", follow_redirects=False
        )
        assert response.status_code == 303
        # Back to the hub with the year, and without a table it has no use for.
        assert response.headers["location"] == f"/nb/arkade?trinn={year}"


def test_a_signed_in_pupil_in_year_eight_is_not_offered_it(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL, year=8)

    assert "/arkade/gangetabellen" not in client.get("/nb/arkade").text
    response = client.get("/nb/arkade/gangetabellen", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/nb/arkade"


def test_the_table_is_the_same_whichever_year_asks() -> None:
    _, client = build(Settings())

    for year in (1, 7):
        page = client.get(f"/nb/arkade/gangetabellen?trinn={year}").text
        assert classes(page, "unasked") == 100


def test_picking_a_year_on_the_hub_keeps_the_table() -> None:
    """A visitor who reaches the hub with a table and no year, and picks one."""
    _, client = build(Settings())
    text = Table({(7, 8): KNOWN}).text

    hub = client.get(f"/nb/arkade?tabell={text}").text

    assert f'href="/nb/arkade?trinn=4&tabell={text}"' in hub.replace("&amp;", "&")


def test_the_hub_reads_no_evidence_for_a_table_it_does_not_carry(pupil, monkeypatch) -> None:
    """A signed-in pupil's table is their evidence, read by the table's own
    pages. The hub carries nothing for them, so it reads nothing."""
    app, client = pupil
    reads = []
    real = app.state.evidence.for_pupil
    monkeypatch.setattr(app.state.evidence, "for_pupil", lambda sub: reads.append(sub) or real(sub))

    client.get("/nb/arkade")

    assert reads == []
