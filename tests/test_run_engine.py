"""The trinntest run: shape, stones, stage stepping, hints and breaks.

The pure parts -- how a run is laid out, when it grows, which hint step comes
next -- are tested without a browser or an app. The rest drives the routes the
way a pupil does, both with htmx (an `HX-Request` header, a partial back) and
without it (a plain form post, a redirect, the whole page), because every
control in a run has to work with scripts off.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from review_helpers import approve_app

from pensum.catalogue.loader import Catalogue
from pensum.i18n import UI_LOCALES, translate
from pensum.items.loader import ItemBank
from pensum.items.schema import AuthoredText, QuizItem
from pensum.items.validate import _hint_problems
from pensum.quiz.scoring import score
from pensum.quiz.session import BREAK_EVERY, DEFAULT_LENGTH, SessionStore, Stones
from pensum.quiz.shape import block, plan, warm_up
from pensum.quiz.stages import lower_stage
from pensum.review.content import fingerprint
from pensum.web.app import create_app as _create_app
from pensum.web.comfort import COMFORT_COOKIE, ComfortProfile
from pensum.web.rendering import templates


def create_app(*args, **kwargs):
    """An app on an instance where an administrator has approved everything.

    Review is not what this module tests, so its pages serve the committed
    content the way an instance does once somebody has done the reviewing.
    """
    app = _create_app(*args, **kwargs)
    approve_app(app)
    return app


# Real goals of MAT01-06 KV1021, so the result page can quote them.
GOALS = ("KM13241", "KM13234", "KM13231", "KM13232")


def text(value: str) -> AuthoredText:
    return AuthoredText(nb=value, en=f"{value} (en)")


def mc(item_id: str, goal: str = "KM13241", difficulty: int = 1, **extra) -> QuizItem:
    return QuizItem.model_validate(
        {
            "id": item_id,
            "goal": goal,
            "type": "multiple_choice",
            "difficulty": difficulty,
            "prompt": text(f"Spørsmål {item_id}"),
            "explanation": text("Fordi."),
            "choices": [
                {"id": "a", "text": text("Ja"), "correct": True},
                {"id": "b", "text": text("Nei")},
                {"id": "c", "text": text("Kanskje")},
            ],
            **extra,
        }
    )


def frame(item_id: str, goal: str = "KM13241", stage: str = "pictorial", **extra) -> QuizItem:
    return QuizItem.model_validate(
        {
            "id": item_id,
            "goal": goal,
            "type": "ten_frame",
            "stage": stage,
            "difficulty": 1,
            "prompt": text(f"Vis 8 ({item_id})"),
            "explanation": text("8 er 5 og 3."),
            "activity": {"alt": text("En tierramme."), "target": 8},
            **extra,
        }
    )


def counters(item_id: str, goal: str = "KM13241", **extra) -> QuizItem:
    return QuizItem.model_validate(
        {
            "id": item_id,
            "goal": goal,
            "type": "counters",
            "stage": "concrete",
            "difficulty": 1,
            "prompt": text(f"Legg 7 ({item_id})"),
            "explanation": text("7 er 5 og 2."),
            "activity": {"alt": text("En matte."), "target": 7},
            **extra,
        }
    )


def frame_state(cells: int) -> str:
    return json.dumps({"frames": [list(range(cells))]})


RIGHT, WRONG = "a", "b"


def pool_of(count: int) -> list[QuizItem]:
    return [mc(f"Q{i:02d}", goal=GOALS[i % 3], difficulty=1 + i % 3) for i in range(count)]


# --- run shape ---------------------------------------------------------------


def test_the_warm_up_is_something_answered_right_before() -> None:
    pool = pool_of(15)
    known = pool[7].id  # difficulty 2: preferred over any easier item
    assert warm_up(pool, [known], seed=1).id == known


def test_without_history_the_warm_up_is_the_easiest_item() -> None:
    pool = pool_of(15)
    for seed in range(10):
        assert warm_up(pool, [], seed=seed).difficulty == 1


def test_a_full_bank_keeps_the_trinntest_length_and_offers_two_to_finish() -> None:
    shaped = plan(pool_of(20), seed=3)
    assert len(shaped.items) == DEFAULT_LENGTH
    assert len(shaped.finish) == 2
    # The slot holds the first option; the second is not in the run at all.
    assert shaped.items[-1] is shaped.finish[0]
    assert shaped.finish[1] not in shaped.items
    ids = [i.id for i in shaped.items] + [shaped.finish[1].id]
    assert len(set(ids)) == len(ids), "no item twice"


def test_a_thin_bank_asks_everything_and_gives_no_choice() -> None:
    shaped = plan(pool_of(6), seed=3)
    assert len(shaped.items) == 6
    assert shaped.finish == ()


def test_the_core_is_blocked_by_goal() -> None:
    shaped = plan(pool_of(20), seed=5)
    goals = [i.goal for i in shaped.core]
    runs = [g for n, g in enumerate(goals) if n == 0 or goals[n - 1] != g]
    assert len(runs) == len(set(goals)), f"a goal appears in two blocks: {goals}"


def test_within_a_goal_concrete_comes_before_pictorial_and_plain() -> None:
    items = [mc("M1"), frame("F1"), counters("C1")]
    assert [i.id for i in block(items)] == ["C1", "F1", "M1"]


# --- stones ------------------------------------------------------------------


def test_stones_fill_as_tasks_finish() -> None:
    assert Stones(done=2, total=5).marks() == ("done", "done", "current", "todo", "todo")
    assert Stones(done=5, total=5).marks() == ("done",) * 5


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_stones_render_as_shapes_with_words_for_a_screen_reader(locale: str) -> None:
    html = templates.get_template("partials/run_stones.html").render(
        stones=Stones(done=3, total=6),
        t=lambda key, **kw: translate(locale, key, **kw),
    )
    assert html.count('class="stone stone--done"') == 3
    assert html.count('class="stone stone--current"') == 1
    assert html.count('class="stone stone--todo"') == 2
    assert translate(locale, "run.stones", done=3, total=6) in html
    assert 'aria-hidden="true"' in html
    # Shape, not colour: no inline style or fill anywhere in the stones.
    assert "style=" not in html
    assert "fill" not in html


# --- stage stepping ----------------------------------------------------------


def session_with(items, pool=(), finish=(), store: SessionStore | None = None):
    # Not `store or ...`: an empty store is falsy, since it has a length.
    store = store if store is not None else SessionStore()
    return store.create(
        subject="MAT01-06",
        goal_set="KV1021",
        grade=2,
        items=list(items),
        # The real clock: the routes look sessions up against it, and a fixed
        # date would expire every planted session two hours after it.
        now=datetime.now(UTC),
        pool=tuple(pool),
        finish_options=tuple(finish),
    )


def test_lower_stage_steps_to_the_nearest_stage_down() -> None:
    abstract = frame("A", stage="abstract")
    pictorial, concrete = frame("P"), counters("C")
    assert lower_stage(abstract, [concrete, pictorial], set()) is pictorial
    assert lower_stage(pictorial, [concrete, pictorial], set()) is concrete
    assert lower_stage(concrete, [concrete, pictorial], set()) is None
    assert lower_stage(pictorial, [concrete], {"C"}) is None, "never an item already used"
    assert lower_stage(mc("M"), [concrete], set()) is None, "no stage, no stepping"


def test_a_wrong_answer_puts_the_lower_stage_next_and_grows_the_run_once() -> None:
    first, second = frame("P1"), frame("P2")
    concrete, concrete2 = counters("C1"), counters("C2")
    pool = [first, second, concrete, concrete2, mc("M1")]
    session = session_with([first, second, mc("M1")], pool)

    session.answer("P1", frame_state(3))
    assert [i.id for i in session.items] == ["P1", "C1", "P2", "M1"]
    assert session.just_grew(first)
    assert session.stones(announcing=True).total == 3, "announced before it is drawn"
    assert session.stones().total == 4

    session.answer("C1", "{}")
    session.answer("P2", frame_state(1))
    assert session.total == 4, "at most one extra stone per run"


def test_a_right_answer_or_no_lower_stage_changes_nothing() -> None:
    session = session_with([frame("P1"), frame("P2")], [frame("P1"), frame("P2")])
    session.answer("P1", frame_state(3))
    assert session.total == 2
    session = session_with([frame("P1"), mc("M1")], [frame("P1"), counters("C1")])
    session.answer("P1", frame_state(8))
    assert session.total == 2


def test_the_last_task_never_grows_the_run() -> None:
    session = session_with([mc("M1"), frame("P1")], [frame("P1"), counters("C1")])
    session.answer("M1", RIGHT)
    session.answer("P1", frame_state(2))
    assert session.total == 2
    assert session.finished


# --- the hint ladder ---------------------------------------------------------


HINTS = {
    "restate": {"nb": "Kortere.", "en": "Shorter."},
    "partial": {"nb": "Først 5.", "en": "First 5."},
    "worked": {"nb": "6 er 5 og 1.", "en": "6 is 5 and 1."},
}


def walk(session, item_id: str, held: str = "") -> list[str]:
    steps = []
    while (step := session.hint(item_id, held)) is not None:
        steps.append(step)
    return steps


def test_a_plain_item_with_nothing_authored_only_restates() -> None:
    session = session_with([mc("M1")])
    assert walk(session, "M1", RIGHT) == ["restate"]
    (shown,) = session.revealed(session.items[0], "nb")
    assert shown.text == "Spørsmål M1", "falls back to the prompt"


def test_the_full_ladder_in_its_fixed_order() -> None:
    item = frame("P1", hints=HINTS)
    session = session_with([item, mc("M1")], [item, counters("C1")])
    assert walk(session, "P1", frame_state(3)) == [
        "restate",
        "show",
        "step_down",
        "partial",
        "worked",
    ]
    revealed = session.revealed(item, "en")
    assert revealed[0].text == "Shorter."
    assert revealed[1].built is not None
    assert revealed[1].text.startswith("So far you have made 3")
    assert revealed[1].task == item.prompt.en
    assert revealed[2].target.id == "C1"


def test_steps_with_no_content_are_skipped() -> None:
    # Typed answer (no script): nothing built, so no "show". No lower stage.
    item = frame("P1", hints={"worked": HINTS["worked"]})
    session = session_with([item])
    assert walk(session, "P1", "8") == ["restate", "worked"]


def test_a_step_is_never_revealed_twice() -> None:
    item = frame("P1", hints=HINTS)
    session = session_with([item])
    session.hint("P1", "")  # restate; nothing built yet
    session.hint("P1", "")  # no board state: show skipped, partial next
    assert session.hint_steps["P1"] == ("restate", "partial")
    # A board built now does not go back down the ladder for "show".
    assert session.hint("P1", frame_state(2)) == "worked"


def test_hints_are_recorded_with_the_answer_and_never_marked_down() -> None:
    hinted, plain = mc("M1", hints={"partial": HINTS["partial"]}), mc("M2")
    session = session_with([hinted, plain])
    walk(session, "M1", RIGHT)
    session.answer("M1", RIGHT)
    session.answer("M2", RIGHT)
    records = {r.item_id: r for r in session.records()}
    assert records["M1"].hints_used == 2
    assert records["M2"].hints_used == 0
    result = score(session)
    assert (result.correct, result.total) == (2, 2)


def test_only_the_task_on_screen_takes_hints() -> None:
    session = session_with([mc("M1"), mc("M2")])
    assert session.hint("M2", "") is None
    assert session.hints_used("M2") == 0


def test_step_down_swaps_the_task_without_growing_the_run() -> None:
    item = frame("P1")
    session = session_with([item, mc("M1")], [item, counters("C1")])
    assert session.swap_down("P1") is None, "only once the step has been offered"
    walk(session, "P1", frame_state(1))
    swapped = session.swap_down("P1")
    assert swapped is not None and swapped.id == "C1"
    assert [i.id for i in session.items] == ["C1", "M1"]
    assert session.hints_used("C1") == 3, "the hints spent come with the task"


def test_a_hints_block_needs_something_in_it() -> None:
    with pytest.raises(ValueError, match="at least one"):
        mc("M1", hints={})


def test_the_validator_catches_a_restatement_that_is_the_prompt() -> None:
    item = mc("M1", hints={"restate": {"nb": "Spørsmål M1", "en": "Other"}})
    assert any("repeats the prompt" in p for p in _hint_problems(item))
    item = mc("M1", hints={"partial": HINTS["partial"], "worked": HINTS["partial"]})
    assert any("same thing" in p for p in _hint_problems(item))
    assert _hint_problems(mc("M1", hints=HINTS)) == []


def test_committed_hints_are_part_of_what_is_approved() -> None:
    """Hints change what a pupil sees, so they are part of the item's
    fingerprint: editing a hint sends an approved item back for review."""
    bank = ItemBank.load()
    hinted = [i for s in bank.item_sets for i in s.items if i.hints is not None]
    assert 6 <= len(hinted) <= 10
    for item in hinted:
        before = fingerprint(item)
        edited = item.model_copy(update={"hints": None})
        assert fingerprint(edited) != before, item.id


# --- the finish --------------------------------------------------------------


def test_choosing_fills_the_finish_slot() -> None:
    a, b = mc("F1"), mc("F2")
    session = session_with([mc("M1"), a], finish=(a, b))
    session.answer("M1", RIGHT)
    assert session.choosing
    assert session.choose("F2") is b
    assert session.items[-1] is b and not session.choosing
    assert session.choose("F1") is None, "one choice"


def test_answering_an_option_directly_counts_as_choosing_it() -> None:
    a, b = mc("F1"), mc("F2")
    session = session_with([mc("M1"), a], finish=(a, b))
    session.answer("M1", RIGHT)
    session.answer("F2", RIGHT)
    assert session.finished
    assert score(session).total == 2


# --- breaks ------------------------------------------------------------------


def test_a_break_is_due_every_four_tasks_until_the_pupil_carries_on() -> None:
    session = session_with(pool_of(10))
    for item in session.items[:BREAK_EVERY]:
        assert not session.break_due()
        session.answer(item.id, RIGHT)
    assert session.break_due()
    session.carry_on()
    assert not session.break_due()


def test_a_partial_run_is_scored_on_what_was_answered_and_says_so() -> None:
    session = session_with(pool_of(10))
    for item in session.items[:4]:
        session.answer(item.id, RIGHT)
    result = score(session)
    assert (result.correct, result.total) == (4, 4)
    assert result.complete is False


# --- over HTTP ---------------------------------------------------------------


@pytest.fixture(scope="module")
def app():
    return create_app(Catalogue.load(), ItemBank.load())


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def with_comfort(client: TestClient, **settings) -> TestClient:
    client.cookies.set(COMFORT_COOKIE, ComfortProfile(**settings).serialise())
    return client


def planted(client: TestClient, items, pool=(), finish=()):
    return session_with(items, pool, finish, store=client.app.state.sessions)


HX = {"HX-Request": "true"}


def test_a_started_quiz_draws_its_stones_before_the_first_question(client: TestClient) -> None:
    start = client.post("/nb/klasse/2/MAT01-06/quiz", follow_redirects=False)
    page = client.get(start.headers["location"]).text
    assert page.count('class="stone stone--') == DEFAULT_LENGTH
    assert translate("nb", "run.stones", done=0, total=DEFAULT_LENGTH) in page
    assert "Spørsmål 1 av" not in page, "stones, not a count"


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_the_feedback_announces_a_new_stone_before_it_appears(
    client: TestClient, locale: str
) -> None:
    first = frame("P1")
    session = planted(client, [first, mc("M1")], [first, counters("C1")])
    feedback = client.post(
        f"/{locale}/quiz/{session.id}/answer",
        data={"item_id": "P1", "response": frame_state(2)},
    ).text
    assert translate(locale, "run.grew") in feedback
    assert feedback.count('class="stone stone--') == 2
    question = client.get(f"/{locale}/quiz/{session.id}/question").text
    assert question.count('class="stone stone--') == 3
    assert translate(locale, "run.grew") not in question


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_help_works_without_a_script(client: TestClient, locale: str) -> None:
    item = mc("M1", hints={"restate": HINTS["restate"], "worked": HINTS["worked"]})
    session = planted(client, [item, mc("M2")])
    page = client.get(f"/{locale}/quiz/{session.id}").text
    help_url = f"/{locale}/quiz/{session.id}/help"
    assert f'formaction="{help_url}" formmethod="post" formnovalidate' in page

    pressed = client.post(help_url, data={"item_id": "M1"}, follow_redirects=False)
    assert pressed.status_code == 303
    assert pressed.headers["location"] == f"/{locale}/quiz/{session.id}"
    page = client.get(pressed.headers["location"]).text
    assert HINTS["restate"][locale] in page
    assert HINTS["worked"][locale] not in page

    client.post(help_url, data={"item_id": "M1"})
    page = client.get(f"/{locale}/quiz/{session.id}").text
    assert HINTS["worked"][locale] in page
    assert translate(locale, "run.help_done") in page
    assert f'formaction="{help_url}"' not in page, "no button with nothing behind it"


def test_help_with_htmx_swaps_the_slot_and_keeps_the_board(client: TestClient) -> None:
    item = frame("P1", hints=HINTS)
    session = planted(client, [item, mc("M1")], [item, counters("C1")])
    url = f"/nb/quiz/{session.id}/help"
    built = frame_state(5)
    client.post(url, data={"item_id": "P1", "response": built}, headers=HX)
    slot = client.post(url, data={"item_id": "P1", "response": built}, headers=HX).text
    assert "<html" not in slot
    assert "hint-so-far" in slot, "step 2 draws what was built beside the task"
    assert "comparison" not in slot, "and never the solution beside it"
    # The board comes back as the pupil left it, not empty.
    held = re.search(r"<input[^>]*data-state[^>]*>", slot)
    assert held is not None
    assert "[[0,1,2,3,4]]" in held.group(0).replace("&#34;", '"')

    slot = client.post(url, data={"item_id": "P1", "response": built}, headers=HX).text
    assert f'formaction="/nb/quiz/{session.id}/swap"' in slot
    swapped = client.post(f"/nb/quiz/{session.id}/swap", data={"item_id": "P1"}, headers=HX)
    assert 'data-activity="counters"' in swapped.text


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_the_finish_is_two_cards_that_work_as_plain_forms(client: TestClient, locale: str) -> None:
    a, b = mc("F1"), mc("F2")
    session = planted(client, [mc("M1"), a], finish=(a, b))
    client.post(f"/{locale}/quiz/{session.id}/answer", data={"item_id": "M1", "response": RIGHT})
    page = client.get(f"/{locale}/quiz/{session.id}").text
    assert translate(locale, "run.choose_heading") in page
    assert page.count('class="finish-card"') == 2
    assert page.count(f'action="/{locale}/quiz/{session.id}/choose"') == 2

    chose = client.post(
        f"/{locale}/quiz/{session.id}/choose", data={"item_id": "F2"}, follow_redirects=False
    )
    assert chose.status_code == 303
    page = client.get(f"/{locale}/quiz/{session.id}").text
    assert 'value="F2"' in page and "finish-card" not in page


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_the_break_card_offers_to_stop_and_the_result_says_it_was_partial(
    client: TestClient, locale: str
) -> None:
    with_comfort(client, break_reminder=True)
    session = planted(client, pool_of(DEFAULT_LENGTH))
    for item in list(session.items)[:BREAK_EVERY]:
        client.post(
            f"/{locale}/quiz/{session.id}/answer", data={"item_id": item.id, "response": RIGHT}
        )
    card = client.get(f"/{locale}/quiz/{session.id}/question").text
    assert translate(locale, "run.break_heading") in card
    assert f'method="post" action="/{locale}/quiz/{session.id}/carry-on"' in card
    assert f'href="/{locale}/quiz/{session.id}/result"' in card

    result = client.get(f"/{locale}/quiz/{session.id}/result").text
    assert translate(locale, "run.partial_note", answered=4, total=DEFAULT_LENGTH) in result
    assert translate(locale, "result.passed") not in result, "no verdict on part of a run"
    assert translate(locale, "result.not_passed") not in result

    carried = client.post(f"/{locale}/quiz/{session.id}/carry-on", follow_redirects=False)
    assert carried.status_code == 303
    page = client.get(f"/{locale}/quiz/{session.id}").text
    assert translate(locale, "run.break_heading") not in page
    assert 'class="question"' in page


def test_no_break_card_unless_asked_for(client: TestClient) -> None:
    session = planted(client, pool_of(DEFAULT_LENGTH))
    for item in list(session.items)[:BREAK_EVERY]:
        client.post(f"/nb/quiz/{session.id}/answer", data={"item_id": item.id, "response": RIGHT})
    page = client.get(f"/nb/quiz/{session.id}/question").text
    assert translate("nb", "run.break_heading") not in page


def test_show_next_round_trips_through_the_settings_page(client: TestClient) -> None:
    page = client.get("/nb/innstillinger").text
    assert not re.search(r'name="show_next" value="1"[^>]*checked', page, re.S)
    saved = client.post(
        "/nb/innstillinger", data={"calm": "1", "show_next": "1"}, follow_redirects=False
    )
    profile = ComfortProfile.parse(saved.cookies[COMFORT_COOKIE])
    assert profile.show_next is True
    assert ComfortProfile.parse(profile.serialise()) == profile
    assert re.search(
        r'name="show_next" value="1"[^>]*checked', client.get("/nb/innstillinger").text, re.S
    )
    assert ComfortProfile().show_next is False


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_show_next_previews_the_next_task(client: TestClient, locale: str) -> None:
    session = planted(client, [mc("M1"), frame("P1")])
    plain = client.get(f"/{locale}/quiz/{session.id}").text
    assert "run-preview" not in plain

    with_comfort(client, show_next=True)
    page = client.get(f"/{locale}/quiz/{session.id}").text
    preview = translate(
        locale,
        "run.next",
        kind=translate(locale, "run.kind.ten_frame"),
        prompt=frame("P1").prompt.get(locale),
    )
    assert preview in page
    client.post(f"/{locale}/quiz/{session.id}/answer", data={"item_id": "M1", "response": RIGHT})
    assert translate(locale, "run.next_last") in client.get(f"/{locale}/quiz/{session.id}").text


def test_the_nivatest_gets_no_run_controls(client: TestClient) -> None:
    started = client.post("/nb/nivatest/MAT01-06", follow_redirects=False)
    page = client.get(started.headers["location"]).text
    assert "stone" not in page
    assert "/help" not in page


# --- hint step 2 never gives the answer away -----------------------------------


def _render_help(item: QuizItem, held: str, locale: str) -> str:
    session = session_with([item])
    session.hint(item.id, held)  # restate
    assert session.hint(item.id, held) == "show"
    shown = [h for h in session.revealed(item, locale) if h.step == "show"]
    return templates.get_template("partials/run_help.html").render(
        hints=shown,
        more_help=False,
        locale=locale,
        t=lambda key, **kw: translate(locale, key, **kw),
    )


def _visible(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _hands_on() -> list[QuizItem]:
    bank = ItemBank.load()
    return [i for s in bank.item_sets for i in s.items if i.activity is not None]


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_help_step_two_never_shows_the_solution(locale: str) -> None:
    """For every committed hands-on item: before an answer, "show" draws the
    pupil's board and names what is on it, and nothing `compare` would put on
    the "asked" side -- not the solved board, not its caption, not its words."""
    items = _hands_on()
    assert items
    for item in items:
        activity = item.activity
        held = activity.serialise(activity.initial())
        html = _render_help(item, held, locale)
        asked = activity.board(activity.solution(), locale)
        solved = templates.get_template("partials/primitives/_board_static.html").render(
            board=asked, label=""
        )
        solved_body = solved[solved.index(">") + 1 :]
        # A board whose solved picture is the one it opens with (a closed-box
        # balance: the pupil reads it, and answers with a number) gives away
        # nothing the question does not already show.
        if asked != activity.board(activity.initial(), locale):
            assert solved_body not in html, f"{item.id}: the solution board is drawn"
        assert translate(locale, "activity.asked_caption") not in html, item.id
        assert "comparison" not in html, item.id
        answer_words = activity.describe(activity.solution(), locale)
        text = _visible(html).replace(item.prompt.get(locale), "")
        made_words = activity.describe(activity.initial(), locale)
        if answer_words != made_words:
            assert answer_words not in text, f"{item.id}: the answer is said"
        assert translate(locale, "run.hint_so_far", made=made_words) in html


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_feedback_after_an_answer_still_compares_with_the_solution(locale: str) -> None:
    """The fix is to the hint only: a wrong answer's feedback still draws what
    was asked beside what was built (activity rule 7)."""
    for item in _hands_on():
        activity = item.activity
        held = activity.serialise(activity.initial())
        if item.is_correct(held):
            continue
        html = templates.get_template("partials/feedback.html").render(
            item=item,
            locale=locale,
            t=lambda key, **kw: translate(locale, key, **kw),
            given=held,
            correct=False,
            finished=False,
            question_url="/q",
            result_url="/r",
        )
        assert translate(locale, "activity.asked_caption") in html, item.id
        assert "comparison-sentence" in html, item.id
