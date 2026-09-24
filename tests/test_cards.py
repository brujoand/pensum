"""The card primitives: sort, sequence, match, label and highlight.

The same properties `tests/test_primitives.py` holds the number boards to --
grading is a pure function of the declared config and one submitted state, a
malformed state is a wrong answer and never an exception, the board carries no
colour, a wrong answer is drawn beside what was asked -- plus the one thing
these five do differently: without a script the question is a choice between
whole arrangements rather than a typed number, and each choice is a state
graded by the same rule as a built one. The page half is in
`tests/test_cards_js.py`.
"""

from __future__ import annotations

import html as htmllib
import json
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.i18n import translate
from pensum.items.loader import ItemBank
from pensum.items.primitives import PRIMITIVES
from pensum.items.primitives.cards import FEWEST_CHOICES, CardBoard, shuffled
from pensum.items.primitives.highlight import split_words
from pensum.items.primitives.label import DIAGRAMS
from pensum.items.schema import AuthoredText, QuizItem
from pensum.web.app import create_app
from pensum.web.rendering import templates

ALT = {"nb": "Et brett", "en": "A board"}
KINDS = ("sort", "sequence", "match", "label", "highlight")


def text(nb: str, en: str | None = None) -> dict:
    return {"nb": nb, "en": en or nb}


def item(kind: str, **activity) -> QuizItem:
    return QuizItem.model_validate(
        {
            "id": f"KM1-{kind}",
            "goal": "KM1",
            "type": kind,
            "difficulty": 1,
            "prompt": AuthoredText(nb="Gjør det", en="Do it"),
            "explanation": AuthoredText(nb="Slik", en="Like this"),
            "activity": {"alt": ALT, **activity},
        }
    )


def state(**fields) -> str:
    return json.dumps(fields)


SORT = {
    "bins": [text("Flyter", "Floats"), text("Synker", "Sinks")],
    "cards": [
        {"text": text("kork", "cork"), "bin": 0},
        {"text": text("stein", "stone"), "bin": 1},
        {"text": text("blad", "leaf"), "bin": 0},
        {"text": text("spiker", "nail"), "bin": 1},
    ],
}
VENN = {
    "bins": [text("A"), text("B")],
    "venn": True,
    "cards": [
        {"text": text("a"), "bin": 0},
        {"text": text("ab"), "bin": "both"},
        {"text": text("b"), "bin": 1},
    ],
}
SEQUENCE = {"cards": [text("egg"), text("larve"), text("puppe"), text("sommerfugl")]}
CYCLE = {**SEQUENCE, "cycle": True}
MATCH = {
    "pairs": [
        {"left": text("smelting"), "right": text("fast til flytende")},
        {"left": text("fordamping"), "right": text("flytende til gass")},
        {"left": text("størkning"), "right": text("flytende til fast")},
    ]
}
LABEL = {
    "diagram": "compass",
    "labels": [
        {"text": text("nord", "north"), "slot": "north"},
        {"text": text("øst", "east"), "slot": "east"},
        {"text": text("sør", "south"), "slot": "south"},
        {"text": text("vest", "west"), "slot": "west"},
    ],
}
HIGHLIGHT = {"unit": "word", "text": "Katten [hopper] opp og [spiser] fisken."}
PROOF = {
    "unit": "sentence",
    "sentences": [
        {"text": text("Ola har en hund.", "Ola has a dog.")},
        {"text": text("Den heter Bamse.", "It is called Bamse."), "mark": True},
        {"text": text("Bamse liker snø.", "Bamse likes snow.")},
        {"text": text("Om kvelden sover han.", "In the evening he sleeps.")},
    ],
}

# One well-formed item per primitive, a right state, a wrong one, and a right
# one written differently where the primitive has such a thing.
CASES = {
    "sort": (SORT, state(place=[0, 1, 0, 1]), state(place=[0, 1, 1, 1]), None),
    "sequence": (
        CYCLE,
        state(order=[0, 1, 2, 3]),
        state(order=[0, 2, 1, 3]),
        state(order=[2, 3, 0, 1]),
    ),
    "match": (MATCH, state(pairs=[0, 1, 2]), state(pairs=[0, 2, 1]), None),
    "label": (LABEL, state(slots=[0, 1, 2, 3]), state(slots=[0, 2, 1, 3]), None),
    "highlight": (HIGHLIGHT, state(marked=[1, 4]), state(marked=[1]), None),
}

MALFORMED = [
    "",
    "   ",
    "{",
    "[]",
    "null",
    "3",
    "{}",
    '{"place": [0, 1, 0]}',
    '{"place": [0, 1, 0, 9]}',
    '{"place": [0, 1, 0, "1"]}',
    '{"place": [0, 1, 0, 1.0]}',
    '{"order": [0, 0, 1, 2]}',
    '{"order": [0, 1, 2, 3, 4]}',
    '{"order": [-1, 1, 2, 3]}',
    '{"pairs": [0, 0, 1]}',
    '{"pairs": [0, 1, 3]}',
    '{"slots": [0, 0, 1, 2]}',
    '{"slots": [0, 1, 2]}',
    '{"marked": [4, 1]}',
    '{"marked": [1, 1]}',
    '{"marked": [1, 99]}',
    '{"marked": "1,4"}',
    '{"marked": [1, 4], "extra": 1}',
    '{"place": null, "order": null, "pairs": null, "slots": null, "marked": null}',
    '{"place": [[0]], "order": [[0]], "pairs": [[0]], "slots": [[0]], "marked": [[0]]}',
    "[" * 5000,
]


@pytest.mark.parametrize("kind", KINDS)
def test_the_right_state_is_right_and_the_wrong_one_is_wrong(kind: str) -> None:
    config, right, wrong, also = CASES[kind]
    question = item(kind, **config)
    assert question.is_correct(right)
    assert not question.is_correct(wrong)
    if also:
        assert question.is_correct(also)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("response", MALFORMED)
def test_a_malformed_state_is_wrong_and_never_crashes(kind: str, response: str) -> None:
    question = item(kind, **CASES[kind][0])
    assert not question.is_correct(response)
    # The feedback of a malformed answer is drawn too, without raising.
    question.response_text(response, "nb")


@pytest.mark.parametrize("kind", KINDS)
def test_a_typed_number_is_not_an_answer_to_a_card_board(kind: str) -> None:
    question = item(kind, **CASES[kind][0])
    assert not question.is_correct("0")
    assert not question.is_correct("nan")


@pytest.mark.parametrize("kind", KINDS)
def test_every_card_primitive_is_registered_with_a_template_and_a_script(kind: str) -> None:
    primitive = PRIMITIVES[kind]
    assert primitive.config is not None
    assert primitive.template == f"partials/primitives/{kind}.html"
    assert primitive.script == f"primitives/{kind}.js"


# --- the no-script road ----------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_without_a_script_it_is_a_choice_with_one_right_answer(kind: str) -> None:
    activity = item(kind, **CASES[kind][0]).activity
    choices = activity.fallback_choices("nb")
    assert FEWEST_CHOICES <= len(choices) <= 4
    right = [value for value, _ in choices if item(kind, **CASES[kind][0]).is_correct(value)]
    assert right == [activity.serialise(activity.solution())]
    # Every option is a state the board admits, and each reads differently.
    assert all(activity.read(value) is not None for value, _ in choices)
    assert len({words for _, words in choices}) == len(choices)


def test_the_right_choice_is_not_always_in_the_same_place() -> None:
    places = set()
    for kind in KINDS:
        activity = item(kind, **CASES[kind][0]).activity
        values = [value for value, _ in activity.fallback_choices("nb")]
        places.add(values.index(activity.serialise(activity.solution())))
    assert len(places) > 1


# --- sort --------------------------------------------------------------------


def test_sort_starts_with_every_card_unsorted() -> None:
    activity = item("sort", **SORT).activity
    assert activity.initial().place == (-1, -1, -1, -1)
    assert not item("sort", **SORT).is_correct(activity.serialise(activity.initial()))


def test_a_venn_has_three_regions_and_both_is_the_middle() -> None:
    question = item("sort", **VENN)
    assert question.activity.regions == 3
    assert question.is_correct(state(place=[0, 1, 2]))
    assert not question.is_correct(state(place=[0, 0, 2]))
    assert question.activity.titles("nb") == ["Bare A", "Begge", "Bare B"]


@pytest.mark.parametrize(
    "change",
    [
        {"venn": True, "bins": [text("A"), text("B"), text("C")]},
        {"cards": [{"text": text("x"), "bin": "both"}, *SORT["cards"][1:]]},
        {"cards": [{"text": text("x"), "bin": 2}, *SORT["cards"][1:]]},
        {"cards": [{"text": text("kork"), "bin": 0}, *SORT["cards"][:3]]},
        {"cards": [{**c, "bin": 0} for c in SORT["cards"]]},
    ],
)
def test_sort_refuses_a_declaration_that_is_not_a_sorting(change: dict) -> None:
    with pytest.raises(ValidationError):
        item("sort", **{**SORT, **change})


# --- sequence ---------------------------------------------------------------


def test_a_line_is_graded_in_order_only() -> None:
    question = item("sequence", **SEQUENCE)
    assert question.is_correct(state(order=[0, 1, 2, 3]))
    assert not question.is_correct(state(order=[1, 2, 3, 0]))


def test_a_cycle_is_graded_up_to_rotation_but_not_reversal() -> None:
    question = item("sequence", **CYCLE)
    for start in range(4):
        assert question.is_correct(state(order=[(start + k) % 4 for k in range(4)]))
    assert not question.is_correct(state(order=[3, 2, 1, 0]))


@pytest.mark.parametrize("config", [SEQUENCE, CYCLE])
def test_a_sequence_never_opens_already_right(config: dict) -> None:
    activity = item("sequence", **config).activity
    assert not activity.grade_state(activity.initial())


def test_the_jumble_is_fixed_and_never_the_identity() -> None:
    for n in range(2, 9):
        order = shuffled("seed", n)
        assert order == shuffled("seed", n)
        assert order != list(range(n))
        assert sorted(order) == list(range(n))


# --- match ------------------------------------------------------------------


def test_a_right_hand_card_is_in_one_row_at_most() -> None:
    activity = item("match", **MATCH).activity
    assert activity.read(state(pairs=[0, -1, -1])) is not None
    assert activity.read(state(pairs=[0, 0, -1])) is None


def test_the_right_hand_column_is_not_shown_in_authored_order() -> None:
    activity = item("match", **MATCH).activity
    assert activity.right_order() != [0, 1, 2]


# --- label ------------------------------------------------------------------


def test_a_label_names_a_place_the_diagram_has() -> None:
    labels = [{**LABEL["labels"][0], "slot": "up"}, *LABEL["labels"][1:]]
    with pytest.raises(ValidationError, match="no place 'up'"):
        item("label", **{**LABEL, "labels": labels})


def test_places_are_numbered_in_the_diagrams_order_not_the_authored_one() -> None:
    reversed_labels = list(reversed(LABEL["labels"]))
    activity = item("label", **{**LABEL, "labels": reversed_labels}).activity
    assert [name for name, _, _ in activity.places()] == ["north", "east", "south", "west"]
    assert activity.describe(activity.solution(), "nb") == "1: nord; 2: øst; 3: sør; 4: vest"


@pytest.mark.parametrize("diagram", sorted(DIAGRAMS))
def test_every_diagram_can_be_labelled(diagram: str) -> None:
    names = DIAGRAMS[diagram].names[:3]
    labels = [{"text": text(n), "slot": n} for n in names]
    question = item("label", diagram=diagram, labels=labels)
    activity = question.activity
    assert question.is_correct(activity.serialise(activity.solution()))
    board = activity.board(activity.initial(), "nb")
    assert board.width > 0 and board.height > 0


# --- highlight --------------------------------------------------------------


def test_words_split_with_their_punctuation_kept_outside() -> None:
    tokens = split_words("«Hei», sa [Ola].")
    assert [t.text for t in tokens] == ["Hei", "sa", "Ola"]
    assert [(t.before, t.after) for t in tokens] == [("«", "»,"), ("", ""), ("", ".")]
    assert [t.mark for t in tokens] == [False, False, True]


@pytest.mark.parametrize(
    "bad", ["[to ord] her og der", "[] tom her", "ingen merket her", "[alt] [er] [merket]"]
)
def test_a_text_must_mark_whole_words_and_not_everything(bad: str) -> None:
    with pytest.raises(ValidationError):
        item("highlight", unit="word", text=bad)


def test_a_sentence_text_is_the_same_sentences_in_both_languages() -> None:
    question = item("highlight", **PROOF)
    assert question.is_correct(state(marked=[1]))
    assert question.activity.describe(question.activity.solution(), "en") == "«It is called Bamse.»"


def test_highlight_takes_one_kind_of_text() -> None:
    with pytest.raises(ValidationError):
        item("highlight", unit="word", sentences=PROOF["sentences"])
    with pytest.raises(ValidationError):
        item("highlight", unit="sentence", text="a [b] c")


def test_committed_card_items_answer_their_own_solution() -> None:
    bank = ItemBank.load(include_unreviewed=True)
    found: dict[str, list[QuizItem]] = {}
    for s in bank.item_sets:
        for i in s.items:
            if i.type in KINDS:
                found.setdefault(i.type, []).append(i)
    assert set(found) == set(KINDS), "every card primitive has committed items"
    for kind, questions in found.items():
        assert len(questions) >= 3, kind
        for question in questions:
            activity = question.activity
            assert not question.reviewed, question.id
            assert question.is_correct(activity.serialise(activity.solution()))
            assert not question.is_correct(activity.serialise(activity.initial()))


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


@pytest.mark.parametrize("kind", KINDS)
def test_the_board_carries_no_colour_of_its_own(kind: str) -> None:
    config, _, wrong, _ = CASES[kind]
    question = item(kind, **config)
    for html in (render_question(question), render_feedback(question, wrong, False)):
        for svg in svgs(html):
            assert "fill=" not in svg
            assert "stroke=" not in svg
            assert "#" not in svg
        assert 'style="color' not in html
        assert "background" not in re.sub(r"<style.*?</style>", "", html, flags=re.S)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_board_says_what_it_shows_in_the_pupils_language(kind: str, locale: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]), locale)
    assert f'aria-label="{ALT[locale]}"' in html


@pytest.mark.parametrize("kind", KINDS)
def test_without_a_script_the_question_is_a_choice_of_arrangements(kind: str) -> None:
    """The live controls are hidden and the state field disabled, so a page
    that runs no script shows the board as a picture and a set of radio
    buttons, each carrying a whole state, and submits the one picked."""
    question = item(kind, **CASES[kind][0])
    html = render_question(question)

    fallback = re.search(
        r'<fieldset class="activity-fallback[^"]*" data-fallback>.*?</fieldset>', html, re.S
    )
    assert fallback, "the choice is there"
    radios = re.findall(
        r'<input type="radio" name="response" value="([^"]*)" required />', fallback.group(0)
    )
    assert len(radios) >= FEWEST_CHOICES
    graded = [question.is_correct(htmllib.unescape(v)) for v in radios]
    assert graded.count(True) == 1
    assert question.activity.fallback_prompt("nb") in fallback.group(0)
    assert 'inputmode="decimal"' not in html

    hidden = re.search(r'<input type="hidden" name="response"[^>]*>', html)
    assert hidden and "disabled" in hidden.group(0)
    value = htmllib.unescape(re.search(r'value="([^"]*)"', hidden.group(0)).group(1))
    assert question.activity.read(value) is not None

    live = re.findall(r"<[^>]*data-live[^>]*>", html)
    assert live and all("hidden" in tag for tag in live)
    assert html.count('type="submit"') == 1


@pytest.mark.parametrize("kind", KINDS)
def test_every_control_is_a_button_that_does_not_submit(kind: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]))
    for tag in re.findall(r"<button[^>]*>", html):
        assert 'type="button"' in tag or 'type="submit"' in tag
    # The menus are the keyboard path and are never part of the form's answer.
    for tag in re.findall(r"<select[^>]*>", html):
        assert "name=" not in tag


def test_the_highlight_buttons_are_no_focus_stop_without_a_script() -> None:
    html = render_question(item("highlight", **HIGHLIGHT))
    tokens = re.findall(r"<button class=\"token\"[^>]*>", html)
    assert len(tokens) == 6
    assert all("disabled" in tag and 'aria-pressed="false"' in tag for tag in tokens)


def test_every_card_is_drawn_in_every_place_it_could_be() -> None:
    html = render_question(item("sort", **SORT))
    assert len(re.findall(r"<li class=\"card\" data-piece", html)) == 4 * 3
    shown = re.findall(r"<li class=\"card\" data-piece[^>]*>", html)
    assert sum("hidden" not in tag for tag in shown) == 4


@pytest.mark.parametrize("kind", KINDS)
def test_a_wrong_answer_shows_what_was_built_beside_what_was_asked(kind: str) -> None:
    config, _, wrong, _ = CASES[kind]
    question = item(kind, **config)
    page = render_feedback(question, wrong, correct=False)

    activity = question.activity
    made = activity.describe(activity.read(wrong), "nb")
    asked = activity.describe(activity.solution(), "nb")
    assert made != asked
    assert (
        htmllib.escape(translate("nb", activity.made_key(), made=made, asked=asked), quote=False)
        in page
    )
    assert page.count('class="comparison-side"') == 2
    assert "✗" not in page and "✘" not in page


def test_the_sort_sentence_says_where_every_card_went() -> None:
    page = render_feedback(item("sort", **SORT), state(place=[0, 1, -1, 0]), correct=False)
    assert (
        "Du la dem slik: Flyter: kork og spiker; Synker: stein; Ikke plassert ennå: blad. "
        "Oppgaven ba om: Flyter: kork og blad; Synker: stein og spiker." in page
    )


def test_the_highlight_sentence_names_the_words() -> None:
    page = render_feedback(
        item("highlight", **HIGHLIGHT), state(marked=[1, 3]), correct=False, locale="en"
    )
    assert "You marked «hopper» and «og». The task asked for «hopper» and «spiser»." in page


def test_a_typed_answer_to_a_card_board_is_said_plainly() -> None:
    page = render_feedback(item("sort", **SORT), "4", correct=False)
    assert translate("nb", "activity.unreadable") in page


def test_the_static_card_board_leaves_out_what_is_not_there() -> None:
    board = item("match", **MATCH).activity.board(item("match", **MATCH).activity.solution(), "nb")
    assert isinstance(board, CardBoard)
    page = render_feedback(item("match", **MATCH), state(pairs=[0, -1, -1]), correct=False)
    comparison = page[page.index('class="comparison"') :]
    assert "data-piece" not in comparison
    assert not re.search(r"\shidden[\s/>]", comparison)
    assert translate("nb", "activity.cards.none") in comparison


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


@pytest.mark.parametrize("kind", KINDS)
def test_a_built_answer_arrives_through_the_one_response_field(
    client: TestClient, kind: str
) -> None:
    config, right, wrong, _ = CASES[kind]
    question = item(kind, **config)

    session_id = _showing(client, question)
    page = client.get(f"/nb/quiz/{session_id}")
    assert f'data-activity="{kind}"' in page.text
    assert f"/static/primitives/{kind}.js" in page.text

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
