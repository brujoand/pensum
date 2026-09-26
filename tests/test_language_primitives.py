"""The language primitives: sound boxes, blending, word and sentence building,
and dialogue.

The same contract as `tests/test_primitives.py` holds them: grading is a pure
function of the declared config and one submitted state, a malformed state is
a wrong answer and never an exception, the question works without a script,
and a wrong answer shows what was built beside what was asked. What is new here
is the no-script road that is a word, a sentence or a pick rather than a
number, and the dialogue's graph, which is validated when the item loads.
"""

from __future__ import annotations

import html as html_text
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from review_helpers import approve_app

from pensum.catalogue.loader import Catalogue
from pensum.i18n import translate
from pensum.items.loader import ItemBank
from pensum.items.primitives import PRIMITIVES, primitive_for, scripts
from pensum.items.primitives.dialogue import MAX_PICKS, outcome_token
from pensum.items.schema import QuizItem
from pensum.web.app import create_app as _create_app
from pensum.web.rendering import templates


def create_app(*args, **kwargs):
    """An app on an instance where an administrator has approved everything.

    Review is not what this module tests, so its pages serve the committed
    content the way an instance does once somebody has done the reviewing.
    """
    app = _create_app(*args, **kwargs)
    approve_app(app)
    return app


ALT = {"nb": "Et brett", "en": "A board"}
STATIC = Path(__file__).parents[1] / "src" / "pensum" / "web" / "static"


def text(value: str = "x") -> dict[str, str]:
    return {"nb": value, "en": value}


def item(kind: str, **activity) -> QuizItem:
    return QuizItem.model_validate(
        {
            "id": f"KM1-{kind}",
            "goal": "KM1",
            "type": kind,
            "difficulty": 1,
            "prompt": text("Gjør det"),
            "explanation": text("Slik"),
            "activity": {"alt": ALT, **activity},
        }
    )


def state(**fields) -> str:
    return json.dumps(fields)


CAFE = {
    "language": "en",
    "partner": {"nb": "Kelneren", "en": "The waiter"},
    "start": "order",
    "nodes": {
        "order": {
            "says": text("What would you like?"),
            "options": [
                {"text": text("Could I have a juice, please?"), "next": "pay"},
                {"text": text("Juice. Now."), "reply": text("Try asking nicely.")},
            ],
        },
        "pay": {
            "says": text("Here you are."),
            "options": [
                {"text": text("Thank you!"), "next": "bye"},
                {"text": text("Where is it?"), "reply": text("Right here!")},
                {"text": text("Thanks a lot!"), "next": "bye"},
            ],
        },
        "bye": {"says": text("Have a nice day!")},
    },
}

BLEND = {
    "language": "en",
    "tiles": [{"text": "sh", "say": "shh"}, {"text": "i"}, {"text": "p"}],
    "choices": [
        {"id": "a", "text": {"nb": "et skip", "en": "a big boat"}},
        {"id": "b", "text": {"nb": "en sau", "en": "a sheep"}},
        {"id": "c", "text": {"nb": "en butikk", "en": "a shop"}},
    ],
    "answer": "a",
}

SENTENCE = {"words": ["hvor", "bor", "du", "?", "."], "accept": ["Hvor bor du?"]}

# Tray order is alphabetical with marks first, so for SENTENCE the tiles are
# ".", "?", "bor", "du", "hvor": indices 0..4.
# One well-formed item per primitive: config, a right state, a wrong one, a
# right no-script answer and a wrong one.
CASES = {
    "sound_boxes": (
        {"word": "kjole", "language": "nb", "sounds": ["kj", "o", "l", "e"]},
        state(counters=4, slots=[-1] * 6),
        state(counters=5, slots=[-1] * 6),
        "4",
        "5",
    ),
    "blend": (
        BLEND,
        state(joined=3, pick="a"),
        state(joined=3, pick="c"),
        "a",
        "b",
    ),
    "word_build": (
        {"parts": ["fot", "ball", "hånd"], "accept": ["fotball"]},
        # Tray order: ball, fot, hånd.
        state(slots=[1, 0]),
        state(slots=[0, 1]),
        "Fotball",
        "fotbal",
    ),
    "sentence_build": (
        SENTENCE,
        state(slots=[4, 2, 3, 1], flipped=[4]),
        state(slots=[4, 2, 3, 1], flipped=[]),
        "Hvor bor du?",
        "hvor bor du?",
    ),
    "dialogue": (
        CAFE,
        state(picks=[0, 2]),
        state(picks=[1, 0]),
        "1",
        "2",
    ),
}

MALFORMED = [
    "",
    "   ",
    "{",
    "{}",
    "[]",
    "null",
    '"a"',
    "{" * 5000,
    '{"counters": "3", "slots": []}',
    '{"counters": 3.0, "slots": [-1, -1, -1, -1, -1, -1]}',
    '{"counters": 1, "slots": [0, -1, -1, -1, -1, 0]}',
    '{"counters": 99, "slots": [-1, -1, -1, -1, -1, -1]}',
    '{"joined": 1, "pick": "a"}',
    '{"joined": 3, "pick": "zzz"}',
    '{"joined": -1, "pick": ""}',
    '{"slots": [0, 0]}',
    '{"slots": [9, -1]}',
    '{"slots": "01"}',
    '{"slots": [4, 2, 3, 0], "flipped": [0]}',
    '{"slots": [4, 2, 3, -1], "flipped": [1]}',
    '{"slots": [4, 2, 3, 0], "flipped": [4, 4]}',
    '{"picks": [7]}',
    '{"picks": [0, 0, 0]}',
    '{"picks": ["0"]}',
    '{"picks": [-1]}',
    '{"extra": 1, "picks": []}',
    "NaN",
    "tretti",
]


# --- the contract every primitive keeps --------------------------------------


@pytest.mark.parametrize("kind", sorted(CASES))
def test_the_right_state_is_right_and_the_wrong_one_is_wrong(kind: str) -> None:
    config, right, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    assert question.is_correct(right)
    assert not question.is_correct(wrong)


@pytest.mark.parametrize("kind", sorted(CASES))
def test_the_no_script_answer_is_graded_against_the_same_target(kind: str) -> None:
    config, _, _, typed, typed_wrong = CASES[kind]
    question = item(kind, **config)
    assert question.is_correct(typed)
    assert question.is_correct(f" {typed} ")
    assert not question.is_correct(typed_wrong)
    assert question.is_correct(question.activity.typed_example())


@pytest.mark.parametrize("kind", sorted(CASES))
@pytest.mark.parametrize("response", MALFORMED)
def test_a_malformed_state_is_wrong_and_never_crashes(kind: str, response: str) -> None:
    question = item(kind, **CASES[kind][0])
    assert question.is_correct(response) is False
    primitive_for(question).compare(question, response, "nb")
    question.response_text(response, "en")


@pytest.mark.parametrize("kind", sorted(CASES))
def test_every_language_primitive_is_registered_with_a_template_and_a_script(kind: str) -> None:
    primitive = PRIMITIVES[kind]
    assert templates.get_template(primitive.template)
    assert primitive.script in scripts()
    assert (STATIC / primitive.script).is_file()


def test_nothing_on_the_page_records() -> None:
    """The voice is the browser's speech synthesis, from text. No script here
    asks for a microphone, and none sends audio anywhere."""
    for kind in CASES:
        source = (STATIC / PRIMITIVES[kind].script).read_text()
        for word in ("getUserMedia", "MediaRecorder", "SpeechRecognition", "fetch(", "XMLHttp"):
            assert word not in source, (kind, word)
    core = (STATIC / "primitives" / "core.js").read_text()
    assert "getUserMedia" not in core and "MediaRecorder" not in core


# --- sound_boxes ---------------------------------------------------------------


def test_sound_boxes_have_more_boxes_than_sounds() -> None:
    """A row of exactly three boxes would answer the question before the word
    was heard."""
    activity = item("sound_boxes", word="sol", language="nb", sounds=["s", "o", "l"]).activity
    assert activity.capacity > len(activity.sounds)


def test_sound_boxes_grade_the_count_then_the_letters() -> None:
    question = item(
        "sound_boxes", word="hus", language="nb", sounds=["h", "u", "s"], letters=True, extra=["m"]
    )
    texts = question.activity.texts
    assert texts == ("h", "m", "s", "u")
    right = [texts.index("h"), texts.index("u"), texts.index("s"), -1, -1]
    assert question.is_correct(state(counters=3, slots=right))
    # The right count without the letters is not yet the answer.
    assert not question.is_correct(state(counters=3, slots=[-1] * 5))
    swapped = [texts.index("h"), texts.index("s"), texts.index("u"), -1, -1]
    assert not question.is_correct(state(counters=3, slots=swapped))
    assert not question.is_correct(state(counters=4, slots=[*right[:3], texts.index("m"), -1]))


def test_a_letter_needs_a_counter_under_it() -> None:
    question = item("sound_boxes", word="hus", language="nb", sounds=["h", "u", "s"], letters=True)
    assert question.activity.read(state(counters=1, slots=[0, 1, -1, -1, -1])) is None


def test_sound_boxes_with_letters_must_spell_the_word() -> None:
    with pytest.raises(ValidationError, match="do not spell"):
        item("sound_boxes", word="hus", language="nb", sounds=["h", "o", "s"], letters=True)
    with pytest.raises(ValidationError, match="letters: true"):
        item("sound_boxes", word="hus", language="nb", sounds=["h", "u", "s"], extra=["m"])


def test_sound_boxes_ask_the_count_of_the_written_word_without_a_script() -> None:
    activity = item("sound_boxes", **CASES["sound_boxes"][0]).activity
    assert "kjole" in activity.fallback_prompt("nb")
    assert activity.fallback_answer() == 4


# --- blend -------------------------------------------------------------------


def test_a_pick_needs_every_tile_on_the_slide() -> None:
    activity = item("blend", **BLEND).activity
    assert activity.read(state(joined=2, pick="a")) is None
    assert activity.read(state(joined=2, pick="")) is not None


def test_blend_refuses_an_answer_that_is_not_a_choice() -> None:
    with pytest.raises(ValidationError, match="not one of the choices"):
        item("blend", **{**BLEND, "answer": "z"})
    with pytest.raises(ValidationError, match="unique"):
        item("blend", **{**BLEND, "choices": [BLEND["choices"][0]] * 2})


def test_a_multi_letter_sound_is_one_tile() -> None:
    activity = item("blend", **BLEND).activity
    assert activity.limits()["count"] == 3
    assert activity.limits()["sounds"][0] == "shh"
    assert activity.word == "ship"


def test_the_word_is_not_said_when_the_item_leaves_blending_to_the_pupil() -> None:
    activity = item("blend", **{**BLEND, "say_word": False}).activity
    assert activity.limits()["word"] == ""
    html = render_question(item("blend", **{**BLEND, "say_word": False}))
    assert 'data-speak="word"' not in html


def test_blend_choices_are_not_shown_in_authored_order_by_accident() -> None:
    activity = item("blend", **BLEND).activity
    assert {c.id for c in activity.shown_choices()} == {"a", "b", "c"}
    assert activity.shown_choices() == item("blend", **BLEND).activity.shown_choices()


# --- word_build ----------------------------------------------------------------


def test_word_build_ignores_case_and_accepts_every_declared_form() -> None:
    question = item("word_build", parts=["hopp", "a", "et"], accept=["hoppet", "hoppa"])
    assert question.is_correct("HOPPET")
    assert question.is_correct("hoppa")
    assert not question.is_correct("hopp")


def test_word_build_refuses_a_word_its_tiles_cannot_build() -> None:
    with pytest.raises(ValidationError, match="cannot be built"):
        item("word_build", parts=["fot", "hånd"], accept=["fotball"])
    with pytest.raises(ValidationError, match="cannot be built"):
        item("word_build", parts=["fot", "ball"], accept=["fotball"], slots=1)


def test_word_build_searches_rather_than_takes_the_longest_tile() -> None:
    question = item("word_build", parts=["fotb", "fot", "ball"], accept=["fotball"])
    assert question.is_correct(question.activity.serialise(question.activity.solution()))


def test_the_frame_is_as_long_as_the_word_unless_the_item_says_otherwise() -> None:
    assert item("word_build", parts=["fot", "ball"], accept=["fotball"]).activity.frame_size == 2
    wider = item("word_build", parts=["fot", "ball"], accept=["fotball"], slots=4).activity
    assert wider.frame_size == 4
    # Gaps close up: the word is read in order, empty places skipped.
    tray = wider.texts  # ball, fot
    assert wider.grade_state(wider.State(slots=(-1, tray.index("fot"), -1, tray.index("ball"))))


# --- sentence_build --------------------------------------------------------------


def test_the_capital_is_a_flip_and_it_is_graded() -> None:
    question = item("sentence_build", **SENTENCE)
    assert question.is_correct(state(slots=[4, 2, 3, 1], flipped=[4]))
    assert not question.is_correct(state(slots=[4, 2, 3, 1], flipped=[]))
    assert not question.is_correct(state(slots=[4, 2, 3, 0], flipped=[4]))


def test_a_mark_cannot_be_flipped() -> None:
    activity = item("sentence_build", **SENTENCE).activity
    assert activity.read(state(slots=[4, 2, 3, 0], flipped=[0])) is None


def test_a_typed_sentence_is_split_into_the_same_tokens() -> None:
    question = item("sentence_build", **SENTENCE)
    assert question.is_correct("Hvor bor du ?")
    assert question.is_correct("  Hvor   bor du?")
    assert not question.is_correct("Hvor bor du.")
    assert not question.is_correct("Hvor bor du")


def test_the_verb_second_transfer_error_is_wrong_and_shown_as_built() -> None:
    config = {
        "words": ["yesterday", "I", "played", "football", "."],
        "accept": ["Yesterday I played football.", "I played football yesterday."],
    }
    question = item("sentence_build", **config)
    activity = question.activity
    assert question.is_correct("I played football yesterday.")
    wrong = activity._state(["Yesterday", "played", "I", "football", "."])
    assert wrong is not None and not activity.grade_state(wrong)
    html = render_feedback(question, activity.serialise(wrong), correct=False, locale="en")
    assert "“Yesterday played I football.”" in html
    assert "“Yesterday I played football.”" in html


def test_a_tile_is_one_word_or_one_mark() -> None:
    with pytest.raises(ValidationError, match="not one word"):
        item("sentence_build", words=["hvor bor", "du", "?"], accept=["Hvor bor du?"])
    with pytest.raises(ValidationError, match="cannot be built"):
        item("sentence_build", words=["hvor", "bor", "du"], accept=["Hvor bor du?"])


# --- dialogue ------------------------------------------------------------------


def nodes(**overrides) -> dict:
    return {**CAFE, "nodes": {**CAFE["nodes"], **overrides}}


def test_a_dialogue_is_graded_on_reaching_the_end() -> None:
    question = item("dialogue", **CAFE)
    # A wrong line first, answered in place, then the right ones: still an end.
    assert question.is_correct(state(picks=[1, 0, 1, 0]))
    assert not question.is_correct(state(picks=[0]))
    assert not question.is_correct(state(picks=[]))


def test_a_pick_after_the_end_or_past_the_limit_is_refused() -> None:
    activity = item("dialogue", **CAFE).activity
    assert activity.read(state(picks=[0, 0, 0])) is None
    assert activity.read(state(picks=[1] * (MAX_PICKS + 1))) is None
    assert activity.read(state(picks=[1] * MAX_PICKS)) is not None


def test_the_solution_is_the_shortest_conversation() -> None:
    activity = item("dialogue", **CAFE).activity
    assert activity.solution().picks == (0, 0)


def test_the_transcript_replays_wrong_picks_with_their_reply() -> None:
    activity = item("dialogue", **CAFE).activity
    lines = activity.transcript(activity.State(picks=(1, 0)), "en")
    assert lines == [
        ("The waiter", "What would you like?"),
        ("You", "Juice. Now."),
        ("The waiter", "Try asking nicely."),
        ("You", "Could I have a juice, please?"),
        ("The waiter", "Here you are."),
    ]


@pytest.mark.parametrize(
    ("config", "problem"),
    [
        ({**CAFE, "start": "nowhere"}, "start 'nowhere' is not a node"),
        (
            nodes(pay={"says": text("Hm"), "options": [{"text": text("a"), "next": "lost"}] * 2}),
            "which is not a node",
        ),
        (
            nodes(extra={"says": text("Nobody comes here")}),
            "no path from 'order' reaches it",
        ),
        (
            nodes(
                pay={
                    "says": text("Again?"),
                    "options": [
                        {"text": text("Yes"), "next": "order"},
                        {"text": text("Bye"), "next": "bye"},
                    ],
                }
            ),
            "might never end",
        ),
        (
            nodes(
                pay={
                    "says": text("Hm"),
                    "options": [
                        {"text": text("a"), "reply": text("no")},
                        {"text": text("b"), "reply": text("no")},
                    ],
                },
            ),
            "no option leads on",
        ),
        (
            nodes(pay={"says": text("Hm"), "options": [{"text": text("a"), "next": "bye"}]}),
            "one option is not a choice",
        ),
    ],
)
def test_a_broken_script_does_not_load(config: dict, problem: str) -> None:
    with pytest.raises(ValidationError, match=re.escape(problem)):
        item("dialogue", **config)


def test_an_option_leads_on_or_is_answered_never_both() -> None:
    both = {"text": text("a"), "next": "bye", "reply": text("no")}
    with pytest.raises(ValidationError, match="either leads on"):
        item("dialogue", **nodes(pay={"says": text("Hm"), "options": [both, both]}))


def test_without_a_script_the_dialogue_is_its_first_turn() -> None:
    question = item("dialogue", **CAFE)
    html = render_question(question)
    fallback = re.search(
        r'<fieldset class="activity-fallback" data-fallback>.*?</fieldset>', html, re.S
    )
    assert fallback
    assert "What would you like?" in fallback.group(0)
    assert fallback.group(0).count('type="radio" name="response"') == 2
    assert not question.is_correct("3")
    assert not question.is_correct("0")
    # A digit that is not an ASCII digit is not an option number, and does
    # not crash on the way to saying so.
    assert not question.is_correct("²")
    render_feedback(question, "²", correct=False)


def _committed(kind: str) -> list[QuizItem]:
    bank = ItemBank.load()
    return [i for s in bank.item_sets for i in s.items if i.type == kind]


def _attribute(page: str, name: str) -> object:
    raw = re.search(rf"{name}='([^']*)'", page)
    assert raw, name
    return json.loads(html_text.unescape(raw.group(1)))


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_dialogue_page_does_not_say_which_line_is_right(locale: str) -> None:
    """Every option's outcome is one opaque token, and a right option's token
    has the same shape as a wrong one's: same length, same alphabet, no null
    and no reply text anywhere on the page until the line is picked."""
    questions = _committed("dialogue")
    assert questions
    for question in questions:
        activity = question.activity
        page = render_question(question, locale)
        limits = _attribute(page, "data-limits")
        tokens = [t for options in limits["nodes"].values() for t in options]
        assert all(isinstance(t, str) and re.fullmatch(r"[0-9a-f]+", t) for t in tokens), (
            question.id
        )
        assert len({len(t) for t in tokens}) == 1, question.id
        start = limits["nodes"][activity.start]
        right = [o.next is not None for o in activity.nodes[activity.start].options]
        assert True in right and False in right, (
            "the start offers both, so the check means something"
        )
        assert "null" not in json.dumps(limits["nodes"])
        script = _attribute(page, "data-script")
        for node in script["nodes"].values():
            assert set(node) == {"says", "options"}, question.id
        for node in activity.nodes.values():
            for option in node.options:
                if option.reply is not None:
                    for text in (option.reply.nb, option.reply.en):
                        assert text not in html_text.unescape(page), (question.id, text)
        assert len(start) == len(right)


def test_an_outcome_token_is_the_outcome_encoded_and_nothing_else() -> None:
    """It decodes (the same XOR again) to where the option leads and the reply."""
    activity = item("dialogue", **CAFE).activity
    tokens = activity.limits()["nodes"]["order"]
    width = len(tokens[0]) // 2
    for index, option in enumerate(activity.nodes["order"].options):
        plain = bytes.fromhex(outcome_token("order", index, " " * width, width))
        spaces = bytes(b ^ 0x20 for b in plain)  # the keystream, recovered
        decoded = bytes(a ^ b for a, b in zip(bytes.fromhex(tokens[index]), spaces, strict=True))
        outcome = json.loads(decoded.decode("ascii"))
        assert outcome["n"] == (option.next or "")
        assert bool(outcome["r"]) == (option.reply is not None)


def test_a_sound_box_never_writes_its_word_on_the_page() -> None:
    """The written word is for a browser with no voice, and the script fills it
    in only after finding none; the server renders the place empty."""
    questions = _committed("sound_boxes")
    assert questions
    for question in questions:
        page = render_question(question)
        written = re.search(r"<p class=\"activity-written\"[^>]*>(.*?)</p>", page, re.S)
        assert written and written.group(1).strip() == "", question.id
        assert "hidden" in written.group(0)


def test_every_option_is_a_button_and_only_the_opening_ones_are_shown() -> None:
    html = render_question(item("dialogue", **CAFE))
    buttons = re.findall(r'<button[^>]*data-action="pick"[^>]*>', html)
    assert len(buttons) == 5
    assert all(("hidden" in b) == ('data-zone="order"' not in b) for b in buttons)


# --- rendering -----------------------------------------------------------------


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
    config, _, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    for html in (render_question(question), render_feedback(question, wrong, False)):
        for svg in svgs(html):
            assert "fill=" not in svg
            assert "stroke=" not in svg
            assert "#" not in svg
            assert 'style="fill' not in svg


@pytest.mark.parametrize("kind", sorted(CASES))
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_board_says_what_it_shows_in_the_pupils_language(kind: str, locale: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]), locale)
    assert f'aria-label="{ALT[locale]}"' in html
    assert len(svgs(html)) == 1


@pytest.mark.parametrize("kind", sorted(CASES))
def test_without_a_script_the_question_is_answerable_in_the_same_form(kind: str) -> None:
    question = item(kind, **CASES[kind][0])
    html = render_question(question)
    fallback = re.search(
        r'<(label|fieldset) class="activity-fallback" data-fallback>.*?</\1>', html, re.S
    )
    assert fallback, "the no-script question is there"
    assert 'name="response"' in fallback.group(0)
    assert "required" in fallback.group(0)

    hidden = re.search(r'<input type="hidden" name="response"[^>]*>', html)
    assert hidden and "disabled" in hidden.group(0)
    value = re.search(r'value="([^"]*)"', hidden.group(0)).group(1).replace("&#34;", '"')
    assert question.activity.read(value) is not None

    live = re.findall(r"<[^>]*data-live[^>]*>", html)
    assert live and all("hidden" in tag for tag in live)
    assert html.count('type="submit"') == 1
    # The voice's buttons and the no-voice notice wait for the script to look.
    for tag in re.findall(r"<[^>]*(?:data-speak|data-no-voice)[^>]*>", html):
        assert "hidden" in tag or "data-speak-tile" in tag


@pytest.mark.parametrize("kind", sorted(CASES))
def test_every_control_is_a_button_that_does_not_submit(kind: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]))
    for tag in re.findall(r"<button[^>]*>", html):
        if "data-action" in tag or "data-speak" in tag:
            assert 'type="button"' in tag


@pytest.mark.parametrize("kind", sorted(CASES))
def test_a_wrong_answer_shows_what_was_built_beside_what_was_asked(kind: str) -> None:
    config, _, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    html = render_feedback(question, wrong, correct=False)
    activity = question.activity
    made = activity.describe(activity.read(wrong), "nb")
    asked = activity.describe(activity.solution(), "nb")
    assert made != asked
    assert translate("nb", activity.made_key(), made=made, asked=asked) in html
    assert len(svgs(html)) == 2
    # The tiles nobody used are part of the question, not of the answer.
    assert "board-layer tray" not in html
    assert "✗" not in html and "✘" not in html


@pytest.mark.parametrize("kind", sorted(CASES))
def test_a_typed_wrong_answer_is_said_literally(kind: str) -> None:
    config, _, _, _, typed_wrong = CASES[kind]
    question = item(kind, **config)
    html = render_feedback(question, typed_wrong, correct=False)
    assert "comparison-sentence" in html
    assert "activity.unreadable" not in html


def test_a_typed_word_is_drawn_in_the_frame_when_the_tiles_can_build_it() -> None:
    question = item("word_build", parts=["fot", "ball", "hånd"], accept=["fotball"])
    html = render_feedback(question, "håndball", correct=False)
    assert translate("nb", "activity.you_wrote", made="håndball", asked="fotball") in html
    assert len(svgs(html)) == 2


# --- committed items -------------------------------------------------------------


def test_committed_language_items_answer_their_own_solution() -> None:
    bank = ItemBank.load()
    found: dict[str, list[QuizItem]] = {}
    for item_set in bank.item_sets:
        for question in item_set.items:
            if question.type in CASES:
                found.setdefault(question.type, []).append(question)
    assert set(found) == set(CASES), "every language primitive has committed items"
    for kind, questions in found.items():
        assert len(questions) >= 3, kind
        for question in questions:
            activity = question.activity
            assert question.is_correct(activity.serialise(activity.solution())), question.id
            assert not question.is_correct(activity.serialise(activity.initial())), question.id
            assert question.is_correct(activity.typed_example()), question.id


# --- over HTTP -------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(Catalogue.load(), ItemBank.load()))


def _showing(client: TestClient, question: QuizItem) -> str:
    start = client.post("/nb/klasse/2/NOR01-08/quiz", follow_redirects=False)
    session_id = start.headers["location"].rsplit("/", 1)[-1]
    session = client.app.state.sessions._sessions[session_id]
    session.items = [question, *session.items[1:]]
    return session_id


@pytest.mark.parametrize("kind", sorted(CASES))
def test_a_built_answer_arrives_through_the_one_response_field(
    client: TestClient, kind: str
) -> None:
    config, right, wrong, typed, _ = CASES[kind]
    question = item(kind, **config)

    session_id = _showing(client, question)
    page = client.get(f"/nb/quiz/{session_id}")
    assert f'data-activity="{kind}"' in page.text
    assert f"/static/{PRIMITIVES[kind].script}" in page.text

    for given, correct in ((right, True), (typed, True), (wrong, False)):
        session_id = _showing(client, question)
        feedback = client.post(
            f"/nb/quiz/{session_id}/answer", data={"item_id": question.id, "response": given}
        ).text
        assert (translate("nb", "quiz.correct") in feedback) is correct, given
