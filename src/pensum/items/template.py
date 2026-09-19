"""One question written once, and asked with different numbers each time.

A hand-written item is one flock of sheep forever. A pupil who meets it twice
meets the same twenty-four animals, and a pupil who meets it three times is
remembering an answer rather than working one out. Practice wants volume, and
volume is what an author cannot supply by hand: three items per goal is three
attempts a pupil will ever get.

**A template is parameters, expressions, and prose that reads them.** The author
declares the free numbers and their ranges, writes every other value as an
expression over them, and interpolates those values into the sentences. Nothing
here is random at request time: the domain is a finite cross product, every
instance in it is built and validated when the file loads, and picking one is
picking from a list.

That last part is the whole reason this is safe to ship. `reviewed: true` on a
hand-written item means somebody read the sentence a child sees. A template
cannot make that promise instance by instance, so it makes a stronger one
instead: the domain is small enough to enumerate, and `instances()` builds every
one of them through the same `QuizItem` validator an authored item goes through.
A domain that can produce a broken question fails at load, not at question time,
and `MAX_DOMAIN` is what keeps "enumerate it all" from being a promise the build
cannot keep.

What a template is not for: any question whose answer is not a function of its
numbers. Naturfag, norsk and RLE items are facts, and a fact does not
parameterise. This is a matematikk feature wearing a general name.

**A template cannot yet be approved from the review page.** `review.queue` walks
`ItemSet.items` and knows nothing about templates, so a template authored with
`reviewed: false` is withheld with no way to change its mind short of editing the
file. `ItemBank` already consults the ledger by template id, so the missing half
is the queue, not the decision. Until then a template is reviewed the way every
item was before the review page existed: in the pull request that adds it.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pensum.items.expr import ExpressionError, evaluate, names, parse
from pensum.items.schema import QuizItem
from pensum.items.text import AuthoredText

__all__ = ["ItemTemplate", "Parameter"]

# How many instances a single template may describe. Small enough that the
# build walks every one of them in well under a second, and large enough that a
# pupil will not exhaust it. An author who wants more is describing a domain
# nobody could review, which is the thing this number exists to prevent.
MAX_DOMAIN = 2000

# `{name}` in a sentence, and nothing more elaborate: no format specs, no
# nesting, no attribute access. A question about sheep does not need them, and
# every one of them is another way for a prompt to fail at question time.
PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class Parameter(BaseModel):
    """A free number, and the values it is allowed to take.

    Inclusive at both ends, and stepped, so `2..20 step 2` is how an author says
    "an even number" without a predicate. Ranges rather than a list because the
    point of the format is to stop anyone typing out instances one by one.
    """

    model_config = ConfigDict(frozen=True)

    min: int
    max: int
    step: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def _check(self) -> Parameter:
        if self.max < self.min:
            raise ValueError(f"a range runs upwards, not {self.min}..{self.max}")
        return self

    def values(self) -> tuple[int, ...]:
        return tuple(range(self.min, self.max + 1, self.step))


class ItemTemplate(BaseModel):
    """A family of questions that differ only in their numbers."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    # Numeric only, for now. A multiple_choice template has to generate its
    # distractors, and a wrong answer that is plausible is a harder thing to
    # compute than a right one; a short_text template has to generate the list
    # of spellings it will accept. Both are real, and neither is this change.
    type: Literal["numeric"] = "numeric"
    difficulty: int = Field(ge=1, le=3)

    # The free numbers. Everything else is computed from these.
    params: dict[str, Parameter] = Field(min_length=1)

    # Named expressions over the parameters and over each other, in order. A
    # derived name exists so the prose can read it: writing `2 * animals` in a
    # sentence is not possible, and should not be -- a sentence interpolates a
    # value, and the arithmetic that produced it belongs up here where the
    # validator can see it.
    derive: dict[str, str] = Field(default_factory=dict)

    # Instances that satisfy none of these are dropped from the domain. This is
    # where an author excludes the degenerate flock: no sheep, one hen, a total
    # a ten-year-old would not be asked for.
    require: tuple[str, ...] = ()

    answer: str = Field(min_length=1)

    prompt: AuthoredText
    explanation: AuthoredText

    reviewed: bool = False
    reviewed_by: str | None = None

    @model_validator(mode="after")
    def _check(self) -> ItemTemplate:
        # Parsing here rather than at instantiation: a typo in an expression is
        # an authoring mistake, and it should stop the file loading rather than
        # surface as a broken question in front of a child.
        known = set(self.params)
        for name, source in self.derive.items():
            if name in known:
                raise ValueError(f"{self.id}: {name} is defined twice")
            unknown = names(self._parse(source, name)) - known
            if unknown:
                raise ValueError(f"{self.id}: {name} reads undefined {sorted(unknown)}")
            known.add(name)

        for index, source in enumerate(self.require):
            unknown = names(self._parse(source, f"require[{index}]")) - known
            if unknown:
                raise ValueError(f"{self.id}: require[{index}] reads undefined {sorted(unknown)}")

        unknown = names(self._parse(self.answer, "answer")) - known
        if unknown:
            raise ValueError(f"{self.id}: answer reads undefined {sorted(unknown)}")

        for field, text in (("prompt", self.prompt), ("explanation", self.explanation)):
            for locale in ("nb", "en"):
                missing = set(PLACEHOLDER.findall(text.get(locale))) - known
                if missing:
                    raise ValueError(
                        f"{self.id}: {field}.{locale} reads undefined {sorted(missing)}"
                    )

        size = 1
        for parameter in self.params.values():
            size *= len(parameter.values())
        if size > MAX_DOMAIN:
            raise ValueError(
                f"{self.id}: {size} combinations is more than the {MAX_DOMAIN} the build "
                f"will enumerate; narrow a range or widen a step"
            )

        if not self.instances():
            raise ValueError(f"{self.id}: no combination satisfies require, so it asks nothing")

        return self

    def _parse(self, source: str, where: str) -> ast.Expression:
        try:
            return parse(source)
        except ExpressionError as error:
            raise ValueError(f"{self.id}: {where}: {error}") from error

    def instances(self) -> tuple[QuizItem, ...]:
        """Every question this template can ask, built and validated.

        The build calls this to check the whole domain; serving calls it to pick
        one. Both get `QuizItem`s that went through the same validator a
        hand-written item does, so nothing downstream can tell the difference --
        which is the point, and is why grading, figures and scoring needed no
        changes to carry this.
        """
        return tuple(self._instance(binding) for binding in self._domain())

    def _domain(self) -> list[dict[str, Any]]:
        """The parameter combinations that survive `require`, in a fixed order.

        Sorted by name and walked in range order, so the nth instance is the nth
        instance on every machine and in every process. A seed that picks a
        question has to pick the same question twice.
        """
        order = sorted(self.params)
        surviving: list[dict[str, Any]] = []
        for combination in _product([self.params[name].values() for name in order]):
            binding = dict(zip(order, combination, strict=True))
            for name, source in self.derive.items():
                try:
                    binding[name] = evaluate(parse(source), binding)
                except ExpressionError:
                    # A combination whose arithmetic does not work is not in the
                    # domain. Dividing by `hens - 4` is a domain that excludes 4,
                    # and saying so by hand in `require` as well would be saying
                    # it twice.
                    binding = {}
                    break
            if binding and all(evaluate(parse(s), binding) for s in self.require):
                surviving.append(binding)
        return surviving

    def _instance(self, binding: dict[str, Any]) -> QuizItem:
        answer = evaluate(parse(self.answer), binding)
        return QuizItem(
            id=f"{self.id}#{'-'.join(str(binding[name]) for name in sorted(self.params))}",
            goal=self.goal,
            type=self.type,
            difficulty=self.difficulty,
            prompt=_fill(self.prompt, binding),
            explanation=_fill(self.explanation, binding),
            answer=answer,
            reviewed=self.reviewed,
            reviewed_by=self.reviewed_by,
        )


def _fill(text: AuthoredText, binding: dict[str, Any]) -> AuthoredText:
    return AuthoredText(
        nb=PLACEHOLDER.sub(lambda m: _number(binding[m.group(1)]), text.nb),
        en=PLACEHOLDER.sub(lambda m: _number(binding[m.group(1)]), text.en),
    )


def _number(value: Any) -> str:
    """A value as it belongs in a sentence a child reads.

    Whole numbers lose the decimal point they never had, and the rest take the
    comma Norwegian writes them with. Same reasoning as `QuizItem.correct_text`.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", ",")


def _product(pools: list[tuple[int, ...]]) -> list[tuple[int, ...]]:
    """`itertools.product`, spelled out to keep the ordering obvious.

    The order is what makes an instance reproducible from a seed, so it is worth
    being able to read it off rather than trusting a recollection of which axis
    varies fastest.
    """
    combinations: list[tuple[int, ...]] = [()]
    for pool in pools:
        combinations = [existing + (value,) for existing in combinations for value in pool]
    return combinations
