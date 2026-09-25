"""Validate authored items against the curriculum catalogue.

Runs as a pre-commit hook and in CI, offline. Schema validity is only half of
it: an item can be perfectly well-formed and still reference a competence goal
that no longer exists, which is exactly what a curriculum revision produces.
That failure is silent at runtime -- the item simply never gets selected -- so it
is made loud here instead.

A template is checked harder than an item, and it has to be. `reviewed: true`
on a hand-written item says a human read the sentence a child will see; on a
template it says a human read a *rule* that produces sentences nobody has read.
What closes that gap is enumeration: every question in the domain is built here,
and every one of them has to be a question worth asking. A domain that can
produce a fraction of a sheep, or an answer of nought, fails the build rather
than surprising a ten-year-old.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.items.loader import DEFAULT_ITEMS_DIR
from pensum.items.schema import BOKMAAL, ENGLISH, QuizItem
from pensum.items.sets import ItemSet
from pensum.items.template import ItemTemplate
from pensum.skills.loader import SkillLibrary
from pensum.skills.schema import SkillFile


def validate(items_dir: Path | None = None, skills: SkillLibrary | None = None) -> list[str]:
    """Return a problem per line. Empty means everything checks out."""
    directory = items_dir or DEFAULT_ITEMS_DIR
    catalogue = Catalogue.load()
    skills = skills if skills is not None else SkillLibrary.load()
    problems: list[str] = []
    item_sets: list[ItemSet] = []

    for path in sorted(directory.glob("*/*.yaml")):
        where = path.relative_to(directory.parent)
        try:
            item_sets.append(
                ItemSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            )
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{where}: {exc}")

    for item_set in item_sets:
        subject = catalogue.subject(item_set.subject)
        if subject is None:
            problems.append(f"{item_set.goal_set}: unknown subject {item_set.subject}")
            continue

        goal_set = subject.goal_set(item_set.goal_set)
        if goal_set is None:
            problems.append(
                f"{item_set.goal_set}: not a goal set of {item_set.subject}; "
                "the curriculum may have been revised"
            )
            continue

        # The check that matters: a renumbered goal orphans its items.
        known = {goal.code for goal in goal_set.goals}
        for item in item_set.items:
            if item.goal not in known:
                problems.append(
                    f"{item.id}: goal {item.goal} is not in {item_set.goal_set}; "
                    "it may have been renumbered by a curriculum revision"
                )
            problems.extend(_skill_problems(item, skills.for_subject(item_set.subject)))
            problems.extend(_hint_problems(item))
        for template in item_set.templates:
            if template.goal not in known:
                problems.append(
                    f"{template.id}: goal {template.goal} is not in {item_set.goal_set}; "
                    "it may have been renumbered by a curriculum revision"
                )
            problems.extend(_domain_problems(template))

        for excused in item_set.not_assessable:
            if excused.goal not in known:
                problems.append(
                    f"{item_set.goal_set}: not_assessable names {excused.goal}, "
                    "which is not in this goal set"
                )

        # Every goal should be either tested or explicitly excused. Silence
        # about a goal is indistinguishable from forgetting it.
        unaccounted = sorted(known - item_set.goals_covered - item_set.goals_excused)
        if unaccounted:
            problems.append(
                f"{item_set.goal_set}: {len(unaccounted)} goal(s) neither tested nor "
                f"marked not_assessable: {', '.join(unaccounted)}"
            )

    return problems


def _skill_problems(item: QuizItem, skill_file: SkillFile | None) -> list[str]:
    """An item that names a skill must name one it can be evidence for.

    Three ways to get it wrong, all silent on the page: a skill id that does not
    exist files evidence under nothing; a skill that is not assessable is
    practised off screen and must never grow from a quiz; and a skill that does
    not cite the item's goal puts the item's evidence under a goal it does not
    test.
    """
    if item.skill is None:
        return []
    skill = skill_file.skill(item.skill) if skill_file is not None else None
    if skill is None:
        return [f"{item.id}: skill {item.skill} is not in this subject's skills file"]
    problems = []
    if not skill.assessable:
        problems.append(f"{item.id}: skill {item.skill} is not assessable, so no item may feed it")
    if item.goal not in skill.refs:
        problems.append(
            f"{item.id}: skill {item.skill} does not cite goal {item.goal}, which this item tests"
        )
    return problems


def _hint_problems(item: QuizItem) -> list[str]:
    """Hints the schema accepts but a pupil would get nothing from.

    The schema checks the block's shape. What it cannot see is a hint that says
    what the pupil already has in front of them: a restatement identical to the
    prompt is the ladder's first step spent on nothing, and two steps with the
    same words are one step shown twice. Both are typos in practice -- a
    copy-paste not yet edited -- so they fail here rather than on a screen.
    """
    hints = item.hints
    if hints is None:
        return []
    problems: list[str] = []
    for locale in (BOKMAAL, ENGLISH):
        prompt = item.prompt.get(locale).strip()
        written = [
            (name, text.get(locale).strip())
            for name, text in (
                ("restate", hints.restate),
                ("partial", hints.partial),
                ("worked", hints.worked),
            )
            if text is not None
        ]
        for name, text in written:
            if text == prompt:
                problems.append(f"{item.id}: hints.{name} ({locale}) repeats the prompt")
        texts = [text for _, text in written]
        if len(set(texts)) != len(texts):
            problems.append(f"{item.id}: two hint steps ({locale}) say the same thing")
    return problems


# The smallest answer worth asking a pupil for. Zero is a legitimate number and
# a terrible generated answer: "how many sauer" answered by "none" reads as a
# trick, and an author who wanted it would say so in `require`.
MIN_ANSWER = 1


def _domain_problems(template: ItemTemplate) -> list[str]:
    """Walk every question a template can ask, and judge each one.

    This is what a template has instead of a human reading its questions. The
    schema already proved each instance is a valid `QuizItem`; what is left is
    whether it is a *sensible* one, and that is arithmetic nobody can eyeball
    across two hundred flocks.
    """
    problems: list[str] = []
    instances = template.instances()

    for item in instances:
        answer = float(item.answer)
        if not answer.is_integer():
            problems.append(
                f"{item.id}: the answer is {answer}, and a question phrased for a whole "
                "number should not produce a fraction"
            )
        elif answer < MIN_ANSWER:
            problems.append(f"{item.id}: the answer is {int(answer)}, which reads as a trick")

    # Two instances that read identically are one question wearing two ids: the
    # pupil meets the same flock twice and the domain is smaller than it looks.
    prompts = [item.prompt.nb for item in instances]
    if len(set(prompts)) != len(prompts):
        repeated = sorted({p for p in prompts if prompts.count(p) > 1})
        problems.append(
            f"{template.id}: {len(repeated)} prompt(s) are produced by more than one "
            "combination, so the domain is smaller than it looks"
        )

    return problems


def main() -> int:
    problems = validate()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s) found in authored items.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
