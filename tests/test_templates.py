"""Questions written once and asked with different numbers.

Two things are being defended here, and they are not the same thing.

The expression evaluator is a parser that must refuse more than it accepts. It
reads strings out of data files, so the interesting tests are the ones that
assert something is *rejected*: a call, an attribute, an import dressed as
arithmetic. A permissive evaluator would pass every test about sheep and still
be the worst change in the repository.

The template itself replaces a human's eyes. `reviewed: true` on a hand-written
item means somebody read the sentence; on a template it means somebody read a
rule, and the enumeration is what turns that back into a promise. So the domain
tests care about the whole domain, not a sample of it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pensum.items.expr import ExpressionError, evaluate, names, parse
from pensum.items.loader import ItemBank
from pensum.items.schema import QuizItem
from pensum.items.sets import ItemSet
from pensum.items.template import MAX_DOMAIN, ItemTemplate
from pensum.items.text import AuthoredText
from pensum.items.validate import _domain_problems


def text(nb: str, en: str | None = None) -> AuthoredText:
    return AuthoredText(nb=nb, en=en or nb)


def farm(**overrides) -> ItemTemplate:
    """The flock question, as a template. Small ranges keep the tests quick."""
    fields = {
        "id": "KM1-T1",
        "goal": "KM1",
        "difficulty": 3,
        "params": {"sheep": {"min": 4, "max": 8}, "hens": {"min": 6, "max": 10}},
        "derive": {"animals": "sheep + hens", "legs": "2 * hens + 4 * sheep"},
        "require": ("sheep >= 2", "hens >= 2"),
        "answer": "sheep",
        "prompt": text("På en gård er det {animals} dyr og {legs} bein."),
        "explanation": text("{sheep} sauer og {hens} høner."),
        "reviewed": True,
    }
    fields.update(overrides)
    return ItemTemplate.model_validate(fields)


# Expressions ---------------------------------------------------------------


def test_arithmetic_evaluates() -> None:
    assert evaluate(parse("2 * hens + 4 * sheep"), {"hens": 14, "sheep": 10}) == 68


def test_comparison_and_chaining_evaluate() -> None:
    assert evaluate(parse("2 <= sheep <= 8"), {"sheep": 4}) is True
    assert evaluate(parse("2 <= sheep <= 8"), {"sheep": 9}) is False


def test_names_reports_what_an_expression_reads() -> None:
    """This is what tells a template which of its fields are free."""
    assert names(parse("2 * hens + 4 * sheep")) == {"hens", "sheep"}


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('true')",
        "open('/etc/passwd')",
        "sheep.__class__",
        "[1, 2, 3]",
        "{'a': 1}",
        "'a string'",
        "lambda: 1",
        "sheep if hens else 0",
        "f'{sheep}'",
    ],
)
def test_anything_that_is_not_arithmetic_is_refused(source: str) -> None:
    """The evaluator reads strings out of data files, so what it refuses is the
    whole security story. Each of these parses as valid Python."""
    with pytest.raises(ExpressionError):
        parse(source)


def test_a_power_is_bounded() -> None:
    """`9 ** 9 ** 9` would hang the build that enumerates the domain."""
    with pytest.raises(ExpressionError, match="power above"):
        evaluate(parse("2 ** n"), {"n": 500})


def test_division_by_zero_is_reported_rather_than_raised() -> None:
    with pytest.raises(ExpressionError, match="division by zero"):
        evaluate(parse("legs / (hens - 4)"), {"legs": 68, "hens": 4})


def test_an_unbound_name_is_reported() -> None:
    with pytest.raises(ExpressionError, match="not defined"):
        evaluate(parse("sheep + goats"), {"sheep": 4})


# Templates -----------------------------------------------------------------


def test_a_template_asks_every_question_in_its_domain() -> None:
    instances = farm().instances()
    assert len(instances) == 25  # 5 sheep values x 5 hen values

    ids = {item.id for item in instances}
    assert len(ids) == len(instances), "each instance needs its own id"


def test_an_instance_is_an_ordinary_item() -> None:
    """Nothing downstream should be able to tell the difference, which is why
    grading, figures and scoring needed no changes to carry this."""
    item = next(i for i in farm().instances() if i.id.endswith("#10-4"))
    assert item.prompt.nb == "På en gård er det 14 dyr og 36 bein."
    assert item.answer == 4
    assert item.is_correct("4") is True
    assert item.is_correct("5") is False


def test_require_prunes_the_domain() -> None:
    narrowed = farm(require=("sheep == hens",))
    assert [item.answer for item in narrowed.instances()] == [6, 7, 8]


def test_a_derived_name_may_read_an_earlier_one() -> None:
    template = farm(
        derive={"animals": "sheep + hens", "legs": "2 * hens + 4 * sheep", "twice": "2 * animals"},
        prompt=text("{twice}"),
    )
    assert any(item.prompt.nb == "28" for item in template.instances())


def test_the_domain_is_ordered_the_same_way_every_time() -> None:
    """A seed that picks a question has to pick the same question twice."""
    assert [i.id for i in farm().instances()] == [i.id for i in farm().instances()]


def test_an_expression_reading_an_undefined_name_is_refused() -> None:
    with pytest.raises(ValidationError, match="reads undefined"):
        farm(derive={"animals": "sheep + goats"})


def test_a_placeholder_with_no_value_is_refused() -> None:
    """Caught at load rather than at question time, where it would be a
    KeyError in front of a child."""
    with pytest.raises(ValidationError, match="reads undefined"):
        farm(prompt=text("{animals} dyr og {goats} geiter"))


def test_defining_a_name_twice_is_refused() -> None:
    with pytest.raises(ValidationError, match="defined twice"):
        farm(derive={"sheep": "1 + 1"})


def test_a_domain_nobody_could_review_is_refused() -> None:
    with pytest.raises(ValidationError, match="more than the"):
        farm(params={"sheep": {"min": 1, "max": 100}, "hens": {"min": 1, "max": 100}})


def test_a_require_that_excludes_everything_is_refused() -> None:
    """A template that asks nothing is a goal silently going untested."""
    with pytest.raises(ValidationError, match="asks nothing"):
        farm(require=("sheep > 500",))


def test_a_range_must_run_upwards() -> None:
    with pytest.raises(ValidationError, match="runs upwards"):
        farm(params={"sheep": {"min": 9, "max": 4}})


def test_a_step_thins_a_range() -> None:
    """How an author says "an even number" without writing a predicate."""
    template = farm(
        params={"sheep": {"min": 4, "max": 12, "step": 4}, "hens": {"min": 6, "max": 6}}
    )
    assert sorted({item.answer for item in template.instances()}) == [4, 8, 12]


def test_a_combination_whose_arithmetic_fails_drops_out() -> None:
    """Dividing by `hens - 6` is a domain that excludes 6, and saying so in
    `require` as well would be saying it twice."""
    template = farm(
        derive={
            "animals": "sheep + hens",
            "legs": "2 * hens + 4 * sheep",
            "each": "legs / (hens - 6)",
        },
        prompt=text("{each}"),
    )
    # hens is the first of the sorted parameters, so it leads the instance id.
    hens = {int(item.id.split("#")[1].split("-")[0]) for item in template.instances()}
    assert 6 not in hens
    assert len(template.instances()) == 20  # the five hens == 6 combinations are gone


# The domain check ----------------------------------------------------------


def test_a_sound_domain_has_no_problems() -> None:
    assert _domain_problems(farm()) == []


def test_a_fractional_answer_is_a_problem() -> None:
    template = farm(answer="legs / 3")
    problems = _domain_problems(template)
    assert problems, "a third of a sheep should not reach a pupil"
    assert "should not produce a fraction" in problems[0]


def test_an_answer_of_nought_is_a_problem() -> None:
    template = farm(answer="sheep - 4")
    assert any("reads as a trick" in problem for problem in _domain_problems(template))


def test_a_domain_that_repeats_itself_is_a_problem() -> None:
    """Two combinations, one sentence: the domain is smaller than it looks."""
    template = farm(prompt=text("{animals} dyr"))
    assert any("smaller than it looks" in problem for problem in _domain_problems(template))


def test_max_domain_is_small_enough_to_enumerate_quickly() -> None:
    """The cap is a promise the build keeps, so it is worth asserting rather
    than trusting: every instance is built on every pre-commit run."""
    assert MAX_DOMAIN <= 2000


# The set -------------------------------------------------------------------


def test_a_template_covers_its_goal() -> None:
    """Otherwise the validator reports the goal as neither tested nor excused."""
    item_set = ItemSet(subject="MAT01-06", goal_set="KV1029", templates=(farm(),))
    assert item_set.goals_covered == {"KM1"}


def test_a_template_may_not_share_an_id_with_an_item() -> None:
    with pytest.raises(ValidationError, match="duplicate item ids"):
        ItemSet(
            subject="MAT01-06",
            goal_set="KV1029",
            templates=(farm(id="dup"), farm(id="dup", goal="KM2")),
        )


# Serving -------------------------------------------------------------------


def bank_with_template(**overrides) -> ItemBank:
    return ItemBank(
        [ItemSet(subject="MAT01-06", goal_set="KV1029", templates=(farm(**overrides),))]
    )


def test_a_template_contributes_one_question_not_its_domain() -> None:
    """Otherwise a quiz of ten is one template ten times over."""
    served = bank_with_template().for_goal_set("KV1029")
    assert len(served) == 1


def test_a_seed_asks_the_same_question_twice() -> None:
    bank = bank_with_template()
    assert bank.for_goal_set("KV1029", seed=7)[0].id == bank.for_goal_set("KV1029", seed=7)[0].id


def test_excluding_a_question_picks_another_rather_than_dropping_the_template() -> None:
    """The nivåtest draws twice for one rung when it deepens, carrying the ids
    it already served. Filtering after the draw would discard the whole template
    whenever its one instance was already spent, and the rung would silently go
    short of the evidence the search asked for.
    """
    bank = bank_with_template()
    first = bank.for_goal_set("KV1029", seed=3)[0]

    again = bank.for_goal_set("KV1029", seed=3, exclude={first.id})
    assert len(again) == 1, "a domain of 25 has more to offer after one is spent"
    assert again[0].id != first.id


def test_a_template_falls_silent_only_when_its_domain_is_spent() -> None:
    bank = bank_with_template()
    every = {item.id for item in farm().instances()}
    assert bank.for_goal_set("KV1029", exclude=every) == []


def test_exclude_still_withholds_an_authored_item() -> None:
    """The argument moved into the bank, so the behaviour it replaced has to
    survive the move."""
    item = QuizItem(
        id="KM1-01",
        goal="KM1",
        type="numeric",
        difficulty=1,
        prompt=text("x"),
        explanation=text("x"),
        answer=1,
        reviewed=True,
    )
    bank = ItemBank([ItemSet(subject="MAT01-06", goal_set="KV1029", items=(item,))])
    assert [i.id for i in bank.for_goal_set("KV1029")] == ["KM1-01"]
    assert bank.for_goal_set("KV1029", exclude={"KM1-01"}) == []


def test_an_unreviewed_template_is_withheld() -> None:
    """Same default as an item: a caller that forgets the argument gets the
    safe answer."""
    bank = bank_with_template(reviewed=False)
    assert bank.for_goal_set("KV1029") == []
    assert len(bank.for_goal_set("KV1029", unreviewed=True)) == 1
