"""The simulations: trials, step code and explore_sim.

The same contract as `tests/test_primitives.py` holds them: grading is a pure
function of the declared config and one submitted state, a malformed state is
a wrong answer and never an exception, the question works without a script,
and nothing on the question page gives the answer away. What is new here is
what each one runs: seeded random draws the server can replay but never grades
on, a program executed on a grid with a hard step limit, and a
predict-observe-explain loop whose prediction is recorded and never marked.
"""

from __future__ import annotations

import html as html_text
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.i18n import translate
from pensum.items.loader import ItemBank
from pensum.items.primitives import PRIMITIVES, primitive_for, scripts
from pensum.items.primitives.step_code import STEP_LIMIT, IfWall, Repeat, StepCodeState
from pensum.items.primitives.trials import MAX_TRIALS, TrialsState, simulate
from pensum.items.schema import QuizItem
from pensum.web.app import create_app
from pensum.web.rendering import templates

ALT = {"nb": "Et brett", "en": "A board"}
STATIC = Path(__file__).parents[1] / "src" / "pensum" / "web" / "static"
KINDS = ("trials", "step_code", "explore_sim")


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


SPINNER = {
    "spinner": [
        {"id": "sol", "label": {"nb": "Sol", "en": "Sun"}, "size": 2},
        {"id": "sky", "label": {"nb": "Sky", "en": "Cloud"}, "size": 1},
        {"id": "regn", "label": {"nb": "Regn", "en": "Rain"}, "size": 1},
    ]
}

ROBOT = {
    "width": 4,
    "height": 3,
    "start": {"x": 0, "y": 2, "facing": "right"},
    "goal": [3, 0],
    "walls": [[1, 1]],
    "tiles": ["step", "left", "right", "repeat", "if_wall"],
    "repeats": [2, 3],
    "solution": [{"repeat": 3, "do": ["step"]}, "left", "step", "step"],
}

MOON = {
    "model": "moon_phase",
    "predict": {
        "prompt": text("Hva ser vi?"),
        "choices": [{"id": "full", "text": text("Fullmåne")}, {"id": "ny", "text": text("Ingen")}],
    },
    "explain": {
        "prompt": text("Hvorfor?"),
        "choices": [
            {"id": "vinkel", "text": text("Vi ser ulike deler av den lyse halvdelen.")},
            {"id": "skygge", "text": text("Jordas skygge dekker den.")},
            {"id": "lyser", "text": text("Den lyser selv.")},
        ],
        "answer": "vinkel",
    },
}

# One well-formed item per primitive: config, a right state, a wrong one, a
# right no-script answer and a wrong one.
CASES = {
    "trials": (
        SPINNER,
        state(prediction="sol", seed=5, done=10, tally=list(simulate(5, 10, [2, 1, 1], 0))),
        state(prediction="sky", seed=5, done=10, tally=list(simulate(5, 10, [2, 1, 1], 0))),
        "sol",
        "equal",
    ),
    "step_code": (
        ROBOT,
        state(program=ROBOT["solution"], cursor=[4]),
        state(program=["step", "step", "step"], cursor=[3]),
        None,  # filled in below: the option number depends on the listing
        None,
    ),
    "explore_sim": (
        MOON,
        state(prediction="ny", locked=True, stop=4, explain="vinkel"),
        state(prediction="full", locked=True, stop=4, explain="skygge"),
        "vinkel",
        "skygge",
    ),
}


def _typed(kind: str) -> tuple[str, str]:
    config, _, _, typed, typed_wrong = CASES[kind]
    if kind != "step_code":
        return typed, typed_wrong
    activity = item(kind, **config).activity
    right = activity.typed_example()
    wrong = next(str(i) for i in range(1, len(activity.options()) + 1) if str(i) != right)
    return right, wrong


MALFORMED = [
    "",
    "   ",
    "{",
    "{}",
    "[]",
    "null",
    '"a"',
    "{" * 5000,
    "[" * 5000,
    '{"prediction": "sol", "seed": 5, "done": 10, "tally": [10, 0, 0]}',
    '{"prediction": null, "seed": 5, "done": 1, "tally": [1, 0, 0]}',
    '{"prediction": "storm", "seed": 5, "done": 0, "tally": [0, 0, 0]}',
    '{"prediction": "sol", "seed": 0, "done": 0, "tally": [0, 0, 0]}',
    '{"prediction": "sol", "seed": 5, "done": 1001, "tally": [0, 0, 0]}',
    '{"prediction": "sol", "seed": 5, "done": "1", "tally": [0, 0, 0]}',
    '{"program": [{"repeat": 2, "do": [{"repeat": 2, "do": [{"repeat": 2, "do": []}]}]}]}',
    '{"program": [{"repeat": 7, "do": []}]}',
    '{"program": ["jump"]}',
    '{"program": [{"repeat": 2, "do": [], "if_wall": []}]}',
    '{"program": ["step"], "cursor": [2]}',
    '{"program": ["step"], "cursor": []}',
    '{"program": "step"}',
    '{"program": [' + ",".join(['"step"'] * 31) + "]}",
    '{"prediction": "full", "locked": false, "stop": 3, "explain": null}',
    '{"prediction": null, "locked": true, "stop": 0, "explain": null}',
    '{"prediction": "full", "locked": false, "stop": 0, "explain": "vinkel"}',
    '{"prediction": "full", "locked": true, "stop": 8, "explain": "vinkel"}',
    '{"prediction": "full", "locked": 1, "stop": 0, "explain": "vinkel"}',
    '{"extra": 1}',
    "NaN",
    "tretti",
    "0",
    "99",
]


# --- the contract every primitive keeps --------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_the_right_state_is_right_and_the_wrong_one_is_wrong(kind: str) -> None:
    config, right, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    assert question.is_correct(right)
    assert not question.is_correct(wrong)


@pytest.mark.parametrize("kind", KINDS)
def test_the_no_script_answer_is_graded_against_the_same_target(kind: str) -> None:
    question = item(kind, **CASES[kind][0])
    typed, typed_wrong = _typed(kind)
    assert question.is_correct(typed)
    assert question.is_correct(f" {typed} ")
    assert not question.is_correct(typed_wrong)
    assert question.is_correct(question.activity.typed_example())


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("response", MALFORMED)
def test_a_malformed_state_is_wrong_and_never_crashes(kind: str, response: str) -> None:
    question = item(kind, **CASES[kind][0])
    assert question.is_correct(response) is False
    primitive_for(question).compare(question, response, "nb")
    question.response_text(response, "en")


@pytest.mark.parametrize("kind", KINDS)
def test_every_simulation_is_registered_with_a_template_and_a_script(kind: str) -> None:
    primitive = PRIMITIVES[kind]
    assert templates.get_template(primitive.template)
    assert primitive.script in scripts()
    assert (STATIC / primitive.script).is_file()


def test_no_script_fetches_anything_or_keeps_a_clock_of_its_own() -> None:
    """The draws come from the seed on the page, and nothing is sent anywhere.
    The one timer is the robot's playback, which calm mode does not start."""
    for kind in KINDS:
        source = (STATIC / PRIMITIVES[kind].script).read_text()
        for word in ("fetch(", "XMLHttp", "Math.random", "setInterval", "Date.now"):
            assert word not in source, (kind, word)
    assert "data-calm" in (STATIC / "primitives" / "step-code.js").read_text()


# --- trials --------------------------------------------------------------------


def test_the_right_prediction_is_worked_out_not_authored() -> None:
    assert item("trials", **SPINNER).activity.right() == "sol"
    assert item("trials", dice=1).activity.right() == "equal"
    assert item("trials", dice=2).activity.right() == "7"
    counted = item(
        "trials", dice=2, question="count", outcome="7", bands=[[0, 9], [10, 24], [25, 100]]
    )
    assert counted.activity.right() == "b1"


@pytest.mark.parametrize(
    "config",
    [
        {
            "spinner": [
                {"id": "a", "label": text(), "size": 2},
                {"id": "b", "label": text(), "size": 2},
                {"id": "c", "label": text(), "size": 1},
            ]
        },  # noqa: E501
        {"dice": 2, "question": "count", "outcome": "7", "bands": [[0, 9], [20, 100]]},
        {"dice": 2, "question": "count", "outcome": "7", "bands": [[0, 20], [15, 100]]},
        {"dice": 2, "question": "count", "outcome": "13", "bands": [[0, 9], [10, 100]]},
        {"dice": 1, "question": "most", "bands": [[0, 9], [10, 100]]},
        {"dice": 1, **SPINNER},
        {
            "spinner": [
                {"id": "equal", "label": text(), "size": 1},
                {"id": "b", "label": text(), "size": 2},
            ]
        },  # noqa: E501
    ],
)
def test_a_trials_item_whose_answer_is_not_clear_does_not_load(config: dict) -> None:
    with pytest.raises(ValidationError):
        item("trials", **config)


def test_grading_reads_the_prediction_and_never_the_draws() -> None:
    """Whatever the seed and however many trials, the same prediction gets the
    same mark: a streak of luck cannot make a good prediction wrong."""
    question = item("trials", **SPINNER)
    activity = question.activity
    for seed in (1, 2, 99, 123456, 2**31 - 1):
        for done in (0, 1, 10, 110, MAX_TRIALS):
            tally = activity.simulate(seed, done)
            for prediction in activity.choices():
                given = activity.serialise(
                    TrialsState(prediction=prediction, seed=seed, done=done, tally=tally)
                )
                assert question.is_correct(given) is (prediction == "sol"), (seed, done)


def test_the_server_replays_the_seed_and_refuses_another_tally() -> None:
    activity = item("trials", **SPINNER).activity
    tally = activity.simulate(42, 100)
    assert sum(tally) == 100
    assert activity.read(state(prediction="sol", seed=42, done=100, tally=list(tally)))
    shifted = [tally[0] - 1, tally[1] + 1, tally[2]]
    assert activity.read(state(prediction="sol", seed=42, done=100, tally=shifted)) is None
    assert activity.read(state(prediction="sol", seed=43, done=100, tally=list(tally))) is None


def test_every_showing_is_issued_its_own_seed() -> None:
    activity = item("trials", **SPINNER).activity
    seeds = {activity.opening().seed for _ in range(20)}
    assert len(seeds) > 15
    assert activity.initial().seed == activity.initial().seed


def test_two_dice_come_up_seven_most_over_many_rolls() -> None:
    tally = simulate(7, MAX_TRIALS, None, 2)
    assert len(tally) == 11 and sum(tally) == MAX_TRIALS
    assert tally.index(max(tally)) == 5


def test_the_tally_is_said_after_the_prediction() -> None:
    activity = item("trials", **SPINNER).activity
    ran = TrialsState(prediction="sky", seed=3, done=1, tally=activity.simulate(3, 1))
    said = activity.describe(ran, "en")
    assert said.startswith("“Cloud”, after 1 spin: ")
    assert activity.describe(activity.initial(), "nb") == translate("nb", "activity.trials.none")


# --- step_code -----------------------------------------------------------------


def robot(**overrides) -> QuizItem:
    return item("step_code", **{**ROBOT, **overrides})


def test_the_executor_stops_at_a_wall_and_at_the_edge() -> None:
    activity = robot().activity
    assert activity.trace(("step", "left", "step")).outcome == "wall"
    assert activity.trace(("left", "step", "step", "step")).outcome == "wall"
    assert activity.trace(("step",)).outcome == "short"
    run = activity.trace(("step", "left", "step"))
    assert run.poses[-1] == (1, 2, 0), "it stops where it was, facing the wall"


def test_the_executor_runs_loops_and_conditions() -> None:
    activity = robot().activity
    loop = (Repeat(repeat=3, do=("step",)), "left", "step", "step")
    assert activity.trace(loop).outcome == "goal"
    condition = (Repeat(repeat=3, do=("step",)), IfWall(if_wall=("left",)), "step", "step")
    assert activity.trace(condition).outcome == "goal"
    # No wall ahead at the start, so the body is skipped.
    assert activity.trace((IfWall(if_wall=("left",)), "step")).poses[-1] == (1, 2, 1)


def test_the_executor_has_a_hard_step_limit() -> None:
    activity = robot(repeats=[3, 9]).activity
    spin = (Repeat(repeat=9, do=(Repeat(repeat=9, do=("left", "left", "left", "left")),)),)
    run = activity.trace(spin)
    assert run.outcome == "limit"
    assert len(run.poses) <= STEP_LIMIT + 1


def test_max_tiles_is_graded() -> None:
    long_way = ("step", "step", "step", "left", "step", "step")
    assert robot().activity.works(long_way)
    assert not robot(max_tiles=5).activity.works(long_way)
    assert robot(max_tiles=5).activity.works(tuple(robot().activity.solution_program))


def test_a_tile_the_item_does_not_offer_is_refused() -> None:
    plain = robot(
        tiles=["step", "left", "right"], solution=["step", "step", "step", "left", "step", "step"]
    )
    assert not plain.is_correct(state(program=ROBOT["solution"], cursor=[4]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"goal": [9, 9]},
        {"walls": [[3, 0]]},
        {"goal": [0, 2]},
        {"solution": ["step"], "walls": []},
        {"tiles": ["left", "right"]},
        {"solution": [{"repeat": 4, "do": ["step"]}]},
    ],
)
def test_a_step_code_item_that_cannot_be_answered_does_not_load(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        robot(**overrides)


def test_the_near_misses_all_fail_and_are_not_marked() -> None:
    activity = robot().activity
    misses = activity.near_misses()
    assert len(misses) >= 2
    assert all(not activity.works(m) for m in misses)
    options = activity.options()
    assert sum(activity.works(p) for p in options) == 1
    html = render_question(robot())
    fallback = re.search(r'<fieldset class="activity-fallback".*?</fieldset>', html, re.S).group(0)
    values = re.findall(r'<input type="radio" name="response" value="([^"]*)"', fallback)
    assert values == [str(i) for i in range(1, len(options) + 1)]
    for tag in re.findall(r"<(?:input|li|label|pre)[^>]*>", fallback):
        assert "checked" not in tag and "correct" not in tag and "data-" not in tag


def test_the_program_as_text_is_generated_from_it() -> None:
    activity = robot(text=True).activity
    assert activity.listing(activity.solution_program, "en") == (
        "for _ in range(3):\n    step()\nturn_left()\nstep()\nstep()"
    )
    assert activity.listing((IfWall(if_wall=()),), "nb") == "if vegg_foran():\n    pass"
    words = robot().activity.listing(activity.solution_program, "en")
    assert words.splitlines()[:3] == ["repeat 3 times", "    step forward", "end"]


def test_the_feedback_draws_the_program_after_it_has_run() -> None:
    activity = robot().activity
    wrong = StepCodeState(program=("step",), cursor=(1,))
    board = activity.outcome_board(wrong, "nb")
    shown = [p for layer in board.layers for p in layer.pieces if p.shown]
    assert {(p.zone, p.index) for p in shown} == {
        ("trail", 8),
        ("trail", 9),
        ("bot", (2 * 4 + 1) * 4 + 1),
    }
    before = activity.board(wrong, "nb")
    assert [
        p for layer in before.layers for p in layer.pieces if p.shown and p.zone == "trail"
    ] == []


# --- explore_sim ---------------------------------------------------------------


def test_the_prediction_is_never_graded() -> None:
    question = item("explore_sim", **MOON)
    for prediction in ("full", "ny"):
        for stop in range(8):
            right = state(prediction=prediction, locked=True, stop=stop, explain="vinkel")
            wrong = state(prediction=prediction, locked=True, stop=stop, explain="skygge")
            assert question.is_correct(right)
            assert not question.is_correct(wrong)


def test_the_prediction_is_not_in_the_feedback() -> None:
    question = item("explore_sim", **MOON)
    given = state(prediction="full", locked=True, stop=4, explain="skygge")
    html = render_feedback(question, given, correct=False)
    assert "Fullmåne" not in html_text.unescape(re.sub(r"<svg.*?</svg>", "", html, flags=re.S))


def test_the_loop_goes_predict_then_watch_then_explain() -> None:
    activity = item("explore_sim", **MOON).activity
    assert activity.read(state(prediction=None, locked=False, stop=0, explain=None))
    assert activity.read(state(prediction="full", locked=False, stop=0, explain=None))
    assert activity.read(state(prediction="full", locked=False, stop=1, explain=None)) is None
    assert activity.read(state(prediction="full", locked=False, stop=0, explain="vinkel")) is None
    assert activity.read(state(prediction="full", locked=True, stop=0, explain="vinkel"))


@pytest.mark.parametrize(
    "config",
    [
        {**MOON, "objects": [{"label": text(), "density": 1}]},
        {**MOON, "model": "states_of_matter", "substance": "water", "temperatures": [20, 100]},
        {**MOON, "model": "states_of_matter", "substance": "water", "temperatures": [50, 20]},
        {**MOON, "model": "floats_sinks", "objects": [{"label": text(), "density": 0.5}]},
        {**MOON, "start": 8},
        {**MOON, "explain": {**MOON["explain"], "answer": "nope"}},
    ],
)
def test_an_explore_sim_item_with_a_bad_model_does_not_load(config: dict) -> None:
    with pytest.raises(ValidationError):
        item("explore_sim", **config)


def test_the_models_say_what_they_show() -> None:
    tank = item(
        "explore_sim",
        **{
            **MOON,
            "model": "floats_sinks",
            "objects": [
                {"label": {"nb": "Korken", "en": "cork"}, "density": 0.24},
                {"label": {"nb": "Steinen", "en": "stone"}, "density": 2.6},
            ],
        },
    ).activity
    assert tank.observation(0, "nb") == "Korken flyter."
    assert tank.observation(1, "en") == "The stone sinks to the bottom."
    box = item(
        "explore_sim",
        **{
            **MOON,
            "model": "states_of_matter",
            "substance": "water",
            "temperatures": [-5, 20, 110],
        },
    ).activity
    assert [box.phase(i) for i in range(3)] == ["solid", "liquid", "gas"]
    moon = item("explore_sim", **MOON).activity
    assert [moon.phase(i) for i in (0, 2, 4, 6)] == [
        "new",
        "first_quarter",
        "full",
        "last_quarter",
    ]


def test_each_stop_is_a_still_and_one_is_shown() -> None:
    activity = item("explore_sim", **MOON).activity
    board = activity.board(activity.initial(), "nb")
    assert len(board.layers) == 8
    assert [("is-off" not in layer.role) for layer in board.layers] == [True] + [False] * 7


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


@pytest.mark.parametrize("kind", KINDS)
def test_the_board_carries_no_colour_of_its_own(kind: str) -> None:
    config, _, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    for html in (render_question(question), render_feedback(question, wrong, False)):
        for svg in svgs(html):
            assert "fill=" not in svg
            assert "stroke=" not in svg
            assert "#" not in svg
            assert 'style="fill' not in svg


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("locale", ["nb", "en"])
def test_the_board_says_what_it_shows_in_the_pupils_language(kind: str, locale: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]), locale)
    assert f'aria-label="{ALT[locale]}"' in html


@pytest.mark.parametrize("kind", KINDS)
def test_without_a_script_the_question_is_answerable_in_the_same_form(kind: str) -> None:
    question = item(kind, **CASES[kind][0])
    html = render_question(question)
    fallback = re.search(
        r'<fieldset class="activity-fallback" data-fallback>.*?</fieldset>', html, re.S
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
    # The slider is a control on the page, not an answer: it has no name.
    for tag in re.findall(r"<input[^>]*type=\"range\"[^>]*>", html):
        assert "name=" not in tag


def test_without_a_script_every_still_is_listed() -> None:
    question = item("explore_sim", **MOON)
    html = render_question(question)
    strip = re.search(r'<ol class="sim-strip">.*?</ol>', html, re.S).group(0)
    assert len(svgs(strip)) == 8
    for i in range(8):
        assert question.activity.observation(i, "nb") in strip


@pytest.mark.parametrize("kind", KINDS)
def test_every_control_is_a_button_that_does_not_submit(kind: str) -> None:
    html = render_question(item(kind, **CASES[kind][0]))
    for tag in re.findall(r"<button[^>]*>", html):
        if "data-action" in tag or "data-run" in tag or "data-frame" in tag or "data-reset" in tag:
            assert 'type="button"' in tag


@pytest.mark.parametrize("kind", KINDS)
def test_a_wrong_answer_shows_what_was_made_beside_what_was_asked(kind: str) -> None:
    config, _, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    html = render_feedback(question, wrong, correct=False)
    activity = question.activity
    made = activity.describe(activity.read(wrong), "nb")
    asked = activity.describe(activity.solution(), "nb")
    assert made != asked
    assert html_text.escape(
        translate("nb", activity.made_key(), made=made, asked=asked), quote=False
    ) in html.replace("&#34;", '"').replace("&#39;", "'")
    assert "✗" not in html and "✘" not in html


@pytest.mark.parametrize("kind", KINDS)
def test_a_typed_wrong_answer_is_said_literally(kind: str) -> None:
    question = item(kind, **CASES[kind][0])
    html = render_feedback(question, _typed(kind)[1], correct=False)
    assert "comparison-sentence" in html
    assert "activity.unreadable" not in html


# --- nothing gives the answer away before it is given ------------------------------


def _committed(kind: str) -> list[QuizItem]:
    bank = ItemBank.load(include_unreviewed=True)
    return [i for s in bank.item_sets for i in s.items if i.type == kind]


def _attribute(page: str, name: str) -> object:
    raw = re.search(rf"{name}='([^']*)'", page)
    assert raw, name
    return json.loads(html_text.unescape(raw.group(1)))


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_a_trials_page_does_not_say_what_to_expect(locale: str) -> None:
    for question in _committed("trials"):
        activity = question.activity
        page = render_question(question, locale)
        limits = _attribute(page, "data-limits")
        assert set(limits) == {"weights", "dice", "outcomes", "choices", "max", "levels"}
        assert limits["choices"] == activity.choices(), "offered in the model's own order"
        say = _attribute(page, "data-say")
        assert set(say["choices"]) == set(activity.choices())
        # No expected count and no share, in any spelling, on the page.
        if activity.question == "count":
            expected = activity.expected()
            for spelling in (f"{float(expected):.1f}", f"{float(expected):.2f}", str(expected)):
                assert spelling not in page and spelling.replace(".", ",") not in page
        for tag in re.findall(r"<(?:button|input)[^>]*>", page):
            assert "correct" not in tag and "checked" not in tag
        hidden = re.search(r'<input type="hidden" name="response" value="([^"]*)"', page)
        opened = json.loads(html_text.unescape(hidden.group(1)))
        assert opened["prediction"] is None and opened["done"] == 0


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_a_step_code_page_does_not_carry_the_solution(locale: str) -> None:
    for question in _committed("step_code"):
        activity = question.activity
        page = render_question(question, locale)
        limits = _attribute(page, "data-limits")
        assert "solution" not in json.dumps(limits)
        solved = json.dumps(activity.solution().model_dump(mode="json")["program"])
        assert solved not in html_text.unescape(page)
        compact = activity.serialise(activity.solution())
        assert compact not in html_text.unescape(page)
        # The live board opens with the robot at the start and no trail.
        assert 'data-zone="trail"' in page
        assert not re.search(
            r'<g class="piece piece--trail"[^>]*data-zone="trail"[^>]*aria-hidden="true">', page
        )


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_an_explore_sim_page_does_not_say_which_explanation_fits(locale: str) -> None:
    for question in _committed("explore_sim"):
        activity = question.activity
        page = render_question(question, locale)
        limits = _attribute(page, "data-limits")
        assert set(limits) == {"stops", "start", "predict", "explain"}
        assert "answer" not in json.dumps(limits)
        buttons = re.findall(r'<button[^>]*data-action="explain"[^>]*>', page)
        shapes = {re.sub(r'data-zone="[^"]*"', "", b) for b in buttons}
        assert len(buttons) == len(activity.explain.choices) and len(shapes) == 1
        # No still, and no label of one, states an explanation.
        stills = " ".join(svgs(page))
        observed = " ".join(activity.observation(i, locale) for i in range(activity.stops()))
        for choice in activity.explain.choices:
            said = choice.text.get(locale)
            assert said not in stills and said not in observed, (question.id, said)


def test_committed_simulation_items_are_drafts_that_answer_their_own_solution() -> None:
    bank = ItemBank.load(include_unreviewed=True)
    found: dict[str, list[QuizItem]] = {}
    for item_set in bank.item_sets:
        for question in item_set.items:
            if question.type in KINDS:
                found.setdefault(question.type, []).append(question)
    assert set(found) == set(KINDS), "every simulation has committed items"
    for kind, questions in found.items():
        assert 3 <= len(questions) <= 4, kind
        for question in questions:
            assert not question.reviewed, question.id
            assert question.skill, question.id
            activity = question.activity
            assert question.is_correct(activity.serialise(activity.solution())), question.id
            assert not question.is_correct(activity.serialise(activity.initial())), question.id
            assert question.is_correct(activity.typed_example()), question.id


def test_the_bug_hunt_opens_on_a_program_that_does_not_work() -> None:
    hunts = [q for q in _committed("step_code") if q.activity.begin]
    assert hunts
    for question in hunts:
        activity = question.activity
        assert activity.trace(activity.begin).outcome != "goal"
        assert activity.text


# --- over HTTP -------------------------------------------------------------------


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
    config, right, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    typed = _typed(kind)[0]

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


@pytest.mark.parametrize("kind", ["trials", "explore_sim"])
def test_the_prediction_is_recorded_with_the_answer(client: TestClient, kind: str) -> None:
    """Not marked, but kept: the submitted state carries it, and the session
    records the response as sent."""
    config, _, wrong, _, _ = CASES[kind]
    question = item(kind, **config)
    session_id = _showing(client, question)
    client.post(f"/nb/quiz/{session_id}/answer", data={"item_id": question.id, "response": wrong})
    records = client.app.state.sessions._sessions[session_id].records()
    [record] = [r for r in records if r.item_id == question.id]
    assert json.loads(record.response)["prediction"] == json.loads(wrong)["prediction"]
    assert record.correct is False
