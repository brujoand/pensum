"""The hands-on item kinds: counters, ten-frames, base-ten blocks, arrays, balances.

Grading is a pure function of the declared config and one submitted state, so
all of it is tested here without a browser: right answers, wrong ones, the
equivalent forms a primitive accepts, and the one property every primitive
must keep -- a malformed state is a wrong answer, never an exception. The page
half, and the check that the page and the server agree, is in
`tests/test_primitives_js.py`.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.i18n import translate
from pensum.items.loader import ItemBank
from pensum.items.primitives import PRIMITIVES, primitive_for, scripts
from pensum.items.schema import AuthoredText, QuizItem
from pensum.web.app import create_app
from pensum.web.rendering import templates

ALT = {"nb": "Et brett", "en": "A board"}


def text(value: str = "x") -> AuthoredText:
    return AuthoredText(nb=value, en=value)


def item(kind: str, **activity) -> QuizItem:
    return QuizItem.model_validate(
        {
            "id": f"KM1-{kind}",
            "goal": "KM1",
            "type": kind,
            "difficulty": 1,
            "prompt": text("Bygg det"),
            "explanation": text("Slik"),
            "activity": {"alt": ALT, **activity},
        }
    )


def state(**fields) -> str:
    return json.dumps(fields)


# One well-formed item per primitive, with a right state, a wrong one, and
# the typed number the no-script road accepts.
CASES = {
    "counters": (
        {"target": 12, "start": 12, "groups": [4, 4, 4]},
        state(loose=0, groups=[4, 4, 4]),
        state(loose=0, groups=[5, 4, 3]),
        "4",
    ),
    "ten_frame": (
        {"target": 8},
        state(frames=[[0, 1, 2, 3, 4, 5, 6, 7]]),
        state(frames=[[0, 1, 2, 3, 4, 5, 6]]),
        "8",
    ),
    "base_ten": (
        {"target": 34},
        state(tens=3, ones=4),
        state(tens=4, ones=3),
        "34",
    ),
    "array": (
        {"rows": 3, "cols": 7, "split": 5},
        state(rows=3, cols=7, split=5),
        state(rows=3, cols=7, split=4),
        "21",
    ),
    "balance": (
        {"left": {"weights": 7}, "right": {"boxes": 1, "weights": 5}, "open_box": True},
        state(left={"boxes": 0, "weights": 7}, right={"boxes": 1, "weights": 5}, box=2),
        state(left={"boxes": 0, "weights": 7}, right={"boxes": 1, "weights": 5}, box=3),
        "2",
    ),
}

# Things a form field can carry that are not a state of any board. Every one
# must be graded wrong, and none may raise.
MALFORMED = [
    "",
    "   ",
    "{",
    "{}",
    "[]",
    "null",
    '"34"',
    "{" * 5000,
    '{"loose": "3"}',
    '{"tens": 3.0, "ones": 4}',
    '{"tens": -1, "ones": 44}',
    '{"rows": 1e9, "cols": 1}',
    '{"frames": [[0, 0, 1]]}',
    '{"frames": "0123"}',
    '{"left": 1, "right": 2, "box": 3}',
    '{"extra": 1, "tens": 3, "ones": 4}',
    "NaN",
    "inf",
    "tretti",
]


@pytest.mark.parametrize("kind", sorted(CASES))
def test_the_right_state_is_right_and_the_wrong_one_is_wrong(kind: str) -> None:
    config, right, wrong, _ = CASES[kind]
    question = item(kind, **config)
    assert question.is_correct(right)
    assert not question.is_correct(wrong)


@pytest.mark.parametrize("kind", sorted(CASES))
def test_the_no_script_answer_is_the_same_target_typed(kind: str) -> None:
    config, _, _, typed = CASES[kind]
    question = item(kind, **config)
    assert question.is_correct(typed)
    assert question.is_correct(f" {typed} ")
    assert not question.is_correct(str(int(typed) + 1))


@pytest.mark.parametrize("kind", sorted(CASES))
@pytest.mark.parametrize("response", MALFORMED)
def test_a_malformed_state_is_wrong_and_never_crashes(kind: str, response: str) -> None:
    config = CASES[kind][0]
    question = item(kind, **config)
    assert question.is_correct(response) is False
    # The feedback path reads the same response, and must survive it too.
    primitive_for(question).compare(question, response, "nb")
    question.response_text(response, "en")


@pytest.mark.parametrize("kind", sorted(CASES))
def test_every_primitive_is_registered_with_a_template_and_a_script(kind: str) -> None:
    primitive = PRIMITIVES[kind]
    assert templates.get_template(primitive.template)
    assert primitive.script in scripts()
    assert scripts()[0] == "primitives/core.js"


def test_the_number_line_is_on_the_seam_too() -> None:
    assert PRIMITIVES["number_line"].owns_figure
    assert "number-line.js" in scripts()


# --- counters --------------------------------------------------------------


def test_counters_count_without_groups() -> None:
    question = item("counters", target=7)
    assert question.is_correct(state(loose=7, groups=[]))
    assert not question.is_correct(state(loose=6, groups=[]))


def test_groups_are_graded_in_any_order_and_nothing_left_outside() -> None:
    question = item("counters", target=9, groups=[2, 3, 4])
    assert question.is_correct(state(loose=0, groups=[4, 2, 3]))
    # The right count, but one counter still on the mat.
    assert not question.is_correct(state(loose=1, groups=[4, 2, 2]))
    # A board with a different number of rings did not come from this one.
    assert not question.is_correct(state(loose=0, groups=[4, 5]))


def test_counters_refuse_groups_that_do_not_add_up() -> None:
    with pytest.raises(ValidationError, match="do not add up"):
        item("counters", target=10, groups=[4, 4])
    with pytest.raises(ValidationError, match="one group"):
        item("counters", target=4, groups=[4])


def test_counters_refuse_more_than_the_mat_holds() -> None:
    question = item("counters", target=7)
    capacity = question.activity.capacity
    assert not question.is_correct(state(loose=capacity + 1, groups=[]))


def test_an_equal_share_asks_for_one_group_without_a_script() -> None:
    question = item("counters", target=15, start=15, groups=[5, 5, 5])
    assert question.activity.fallback_prompt("nb") == translate("nb", "activity.counters.ask_each")
    assert question.is_correct("5")
    assert not question.is_correct("15")


# --- ten_frame --------------------------------------------------------------


def test_a_ten_frame_is_graded_on_count_in_any_cells() -> None:
    question = item("ten_frame", target=3)
    assert question.is_correct(state(frames=[[0, 5, 9]]))


def test_in_order_asks_for_the_top_row_first_and_the_first_frame_first() -> None:
    question = item("ten_frame", frames=2, target=13, order="in_order")
    assert question.is_correct(state(frames=[list(range(10)), [0, 1, 2]]))
    assert not question.is_correct(state(frames=[list(range(9)), [0, 1, 2, 3]]))
    assert not question.is_correct(state(frames=[list(range(10)), [5, 6, 7]]))


def test_a_make_ten_frame_asks_how_many_to_add_without_a_script() -> None:
    question = item("ten_frame", target=10, start=7)
    assert question.is_correct("3")
    assert not question.is_correct("10")


def test_a_ten_frame_refuses_a_target_bigger_than_its_frames() -> None:
    with pytest.raises(ValidationError, match="hold 10"):
        item("ten_frame", target=13)


def test_a_ten_frame_refuses_a_cell_that_is_not_there() -> None:
    question = item("ten_frame", target=1)
    assert not question.is_correct(state(frames=[[10]]))
    assert not question.is_correct(state(frames=[[0], [1]]))


# --- base_ten ---------------------------------------------------------------


def test_any_equivalent_accepts_a_broken_ten() -> None:
    question = item("base_ten", target=34)
    assert question.is_correct(state(tens=2, ones=14))
    assert question.is_correct(state(hundreds=0, tens=3, ones=4))


def test_canonical_wants_at_most_nine_in_a_place() -> None:
    question = item("base_ten", target=34, accept="canonical")
    assert question.is_correct(state(tens=3, ones=4))
    assert not question.is_correct(state(tens=2, ones=14))


def test_hundreds_need_flats() -> None:
    with pytest.raises(ValidationError, match="flats"):
        item("base_ten", target=134)
    assert not item("base_ten", target=34).is_correct(state(hundreds=1, tens=0, ones=0))
    question = item("base_ten", target=134, flats=True)
    assert question.is_correct(state(hundreds=1, tens=3, ones=4))
    assert question.is_correct(state(hundreds=0, tens=13, ones=4))


def test_a_mat_cannot_hold_more_than_twenty_of_a_block() -> None:
    assert not item("base_ten", target=21).is_correct(state(tens=0, ones=21))


# --- array ------------------------------------------------------------------


def test_an_exact_array_is_graded_on_rows_then_columns() -> None:
    question = item("array", rows=3, cols=5)
    assert question.is_correct(state(rows=3, cols=5))
    assert not question.is_correct(state(rows=5, cols=3))


def test_either_way_accepts_the_array_turned() -> None:
    question = item("array", rows=4, cols=6, accept="either_way")
    assert question.is_correct(state(rows=6, cols=4))
    assert not question.is_correct(state(rows=3, cols=8))


def test_product_accepts_any_rectangle_of_that_area() -> None:
    question = item("array", rows=3, cols=4, accept="product")
    for rows, cols in ((1, 12), (2, 6), (3, 4), (6, 2)):
        assert question.is_correct(state(rows=rows, cols=cols)) is (rows <= 10 and cols <= 10)
    assert not question.is_correct(state(rows=2, cols=5))


def test_a_split_must_be_inside_the_array_and_graded_exactly() -> None:
    with pytest.raises(ValidationError, match="not inside"):
        item("array", rows=3, cols=5, split=5)
    with pytest.raises(ValidationError, match="exactly"):
        item("array", rows=3, cols=7, split=5, accept="either_way")
    assert not item("array", rows=3, cols=4).is_correct(state(rows=3, cols=4, split=4))


# --- balance ----------------------------------------------------------------


def test_the_box_value_is_computed_not_authored() -> None:
    question = item("balance", left={"boxes": 2, "weights": 3}, right={"weights": 11})
    assert question.activity.box_value == 4
    assert question.is_correct("4")


def test_a_balance_with_no_whole_answer_is_refused() -> None:
    with pytest.raises(ValidationError, match="no whole number"):
        item("balance", left={"boxes": 2, "weights": 3}, right={"weights": 10})
    with pytest.raises(ValidationError, match="unknowable"):
        item("balance", left={"boxes": 1, "weights": 3}, right={"boxes": 1, "weights": 3})
    with pytest.raises(ValidationError, match="no box"):
        item("balance", left={"weights": 3}, right={"weights": 3})


def test_taking_the_same_from_both_sides_is_a_state_the_board_admits() -> None:
    question = item("balance", left={"boxes": 3, "weights": 2}, right={"boxes": 1, "weights": 10})
    solved = state(left={"boxes": 2, "weights": 0}, right={"boxes": 0, "weights": 8}, box=4)
    assert question.is_correct(solved)


def test_taking_from_one_side_only_is_not() -> None:
    question = item("balance", left={"boxes": 3, "weights": 2}, right={"boxes": 1, "weights": 10})
    lopsided = state(left={"boxes": 3, "weights": 0}, right={"boxes": 1, "weights": 10}, box=4)
    assert not question.is_correct(lopsided)


# --- the schema -------------------------------------------------------------


def test_the_activity_kind_comes_from_the_type() -> None:
    assert item("base_ten", target=34).activity.kind == "base_ten"


def test_a_misspelt_parameter_is_refused_rather_than_ignored() -> None:
    with pytest.raises(ValidationError):
        item("base_ten", targte=34)


def test_a_primitive_item_needs_its_activity_and_nothing_else() -> None:
    with pytest.raises(ValidationError):
        QuizItem(
            id="x",
            goal="KM1",
            type="base_ten",
            difficulty=1,
            prompt=text(),
            explanation=text(),
        )
    with pytest.raises(ValidationError, match="never be read"):
        QuizItem.model_validate(
            {
                "id": "x",
                "goal": "KM1",
                "type": "base_ten",
                "difficulty": 1,
                "prompt": text(),
                "explanation": text(),
                "answer": 34,
                "activity": {"alt": ALT, "target": 34},
            }
        )


def test_a_plain_item_cannot_carry_an_activity() -> None:
    with pytest.raises(ValidationError, match="no activity"):
        QuizItem.model_validate(
            {
                "id": "x",
                "goal": "KM1",
                "type": "numeric",
                "difficulty": 1,
                "prompt": text(),
                "explanation": text(),
                "answer": 3,
                "activity": {"kind": "base_ten", "alt": ALT, "target": 34},
            }
        )


def test_stage_is_optional_and_named() -> None:
    assert item("base_ten", target=3).stage is None
    staged = QuizItem.model_validate(
        {
            "id": "x",
            "goal": "KM1",
            "type": "numeric",
            "difficulty": 1,
            "prompt": text(),
            "explanation": text(),
            "answer": 3,
            "stage": "abstract",
        }
    )
    assert staged.stage == "abstract"
    with pytest.raises(ValidationError):
        QuizItem.model_validate({**staged.model_dump(), "stage": "sideways"})


def test_committed_hands_on_items_answer_their_own_solution() -> None:
    bank = ItemBank.load(include_unreviewed=True)
    found = {i.type: i for s in bank.item_sets for i in s.items if i.type in CASES}
    assert set(found) == set(CASES), "every primitive has at least one committed item"
    for question in found.values():
        activity = question.activity
        assert question.is_correct(activity.serialise(activity.solution()))
        assert question.is_correct(str(activity.fallback_answer()))


# --- rendering --------------------------------------------------------------


def render_question(question: QuizItem, locale: str = "nb") -> str:
    return templates.get_template("partials/question.html").render(
        item=question,
        locale=locale,
        t=lambda key, **kwargs: translate(locale, key, **kwargs),
        answer_url="/nb/quiz/x/answer",
        result_url="/nb/quiz/x/result",
        progress="1",
        drafts_visible=False,
    )


def render_feedback(question: QuizItem, given: str, correct: bool, locale: str = "nb") -> str:
    return templates.get_template("partials/feedback.html").render(
        item=question,
        locale=locale,
        t=lambda key, **kwargs: translate(locale, key, **kwargs),
        given=given,
        correct=correct,
        finished=False,
        question_url="/q",
        result_url="/r",
    )


def svgs(html: str) -> list[str]:
    return re.findall(r"<svg.*?</svg>", html, flags=re.S)


@pytest.mark.parametrize("kind", sorted(CASES))
def test_the_board_carries_no_colour_of_its_own(kind: str) -> None:
    question = item(kind, **CASES[kind][0])
    for html in (render_question(question), render_feedback(question, CASES[kind][2], False)):
        for svg in svgs(html):
            assert "fill=" not in svg
            assert "stroke=" not in svg
            assert "#" not in svg
            assert 'style="fill' not in svg


@pytest.mark.parametrize("kind", sorted(CASES))
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_board_says_what_it_shows_in_the_pupils_language(kind: str, locale: str) -> None:
    question = item(kind, **CASES[kind][0])
    html = render_question(question, locale)
    assert f'aria-label="{ALT[locale]}"' in html
    assert len(svgs(html)) == 1


@pytest.mark.parametrize("kind", sorted(CASES))
def test_without_a_script_the_question_is_a_typed_number(kind: str) -> None:
    """The live controls are hidden and the state field disabled, so a page
    that runs no script shows a picture and a box, and submits the box."""
    question = item(kind, **CASES[kind][0])
    html = render_question(question)

    fallback = re.search(
        r"<label class=\"activity-fallback\" data-fallback>.*?</label>", html, re.S
    )
    assert fallback, "the typed question is there"
    assert 'name="response"' in fallback.group(0)
    assert "required" in fallback.group(0)
    assert question.activity.fallback_prompt("nb") in fallback.group(0)

    hidden = re.search(r'<input type="hidden" name="response"[^>]*>', html)
    assert hidden and "disabled" in hidden.group(0)
    # Its value is the opening board, and it is a state the board admits.
    value = re.search(r'value="([^"]*)"', hidden.group(0)).group(1).replace("&#34;", '"')
    assert question.activity.read(value) is not None

    live = re.findall(r"<[^>]*data-live[^>]*>", html)
    assert live and all("hidden" in tag for tag in live)
    # Check stays the ordinary submit button: nothing else submits.
    assert html.count('type="submit"') == 1


@pytest.mark.parametrize("kind", sorted(CASES))
def test_every_control_is_a_button_that_does_not_submit(kind: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]))
    for tag in re.findall(r"<button[^>]*data-action[^>]*>", html):
        assert 'type="button"' in tag


@pytest.mark.parametrize("kind", sorted(CASES))
def test_a_wrong_answer_shows_what_was_built_beside_what_was_asked(kind: str) -> None:
    config, right, wrong, _ = CASES[kind]
    question = item(kind, **config)
    html = render_feedback(question, wrong, correct=False)

    made = question.activity.describe(question.activity.read(wrong), "nb")
    asked = question.activity.describe(question.activity.solution(), "nb")
    assert made != asked
    assert translate("nb", "activity.you_made", made=made, asked=asked) in html
    assert len(svgs(html)) == 2
    # Nothing about it is a mark against the pupil: no cross, no "wrong".
    assert "✗" not in html and "✘" not in html and "×</" not in html


def test_the_sentence_is_literal_about_a_swapped_number() -> None:
    question = item("base_ten", target=34)
    html = render_feedback(question, state(tens=4, ones=3), correct=False)
    assert "Du laget 43 (4 tiere og 3 enere). Oppgaven var 34 (3 tiere og 4 enere)." in html


def test_a_typed_wrong_answer_is_drawn_too_where_it_can_be() -> None:
    question = item("base_ten", target=34)
    html = render_feedback(question, "43", correct=False, locale="en")
    assert "You wrote 43. The answer is 34." in html
    assert len(svgs(html)) == 2


def test_an_unreadable_state_is_said_plainly_and_the_task_still_drawn() -> None:
    question = item("base_ten", target=34)
    html = render_feedback(question, "{nonsense", correct=False)
    assert translate("nb", "activity.unreadable") in html
    assert len(svgs(html)) == 1


def test_a_right_answer_shows_no_comparison() -> None:
    config, right, _, _ = CASES["counters"]
    html = render_feedback(item("counters", **config), right, correct=True)
    assert "comparison" not in html


# --- over HTTP --------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(Catalogue.load(), ItemBank.load()))


def _showing(client: TestClient, question: QuizItem) -> str:
    start = client.post("/nb/klasse/2/MAT01-06/quiz", follow_redirects=False)
    session_id = start.headers["location"].rsplit("/", 1)[-1]
    session = client.app.state.sessions._sessions[session_id]
    session.items = [question, *session.items[1:]]
    return session_id


@pytest.mark.parametrize("kind", sorted(CASES))
def test_a_built_answer_arrives_through_the_one_response_field(
    client: TestClient, kind: str
) -> None:
    config, right, wrong, _ = CASES[kind]
    question = item(kind, **config)

    session_id = _showing(client, question)
    page = client.get(f"/nb/quiz/{session_id}")
    assert f'data-activity="{kind}"' in page.text
    assert "/static/primitives/core.js" in page.text
    assert f"/static/{PRIMITIVES[kind].script}" in page.text

    right_feedback = client.post(
        f"/nb/quiz/{session_id}/answer", data={"item_id": question.id, "response": right}
    ).text
    assert translate("nb", "quiz.correct") in right_feedback

    session_id = _showing(client, question)
    wrong_feedback = client.post(
        f"/nb/quiz/{session_id}/answer", data={"item_id": question.id, "response": wrong}
    ).text
    assert translate("nb", "quiz.correct") not in wrong_feedback
    assert "comparison-sentence" in wrong_feedback


def test_the_static_scripts_are_served(client: TestClient) -> None:
    for script in scripts():
        response = client.get(f"/static/{script}")
        assert response.status_code == 200, script
