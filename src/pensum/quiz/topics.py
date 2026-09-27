"""Topics: a checkpoint's quiz narrowed to one strand, for drilling.

A topic is a strand of the subject's skills file (`data/skills/`), such as "Form
og rom". Items are not tagged with a topic directly. An item already names its
skill, or is attributed to skills through its goal, and each skill sits in one
strand. The topic is read off that chain, so the one tag an author writes
(`skill:`) keeps the topic right as well, and no item can fall outside every
topic without also falling outside every skill.

Attribution to strands is broader than `pensum.mastery.attribution` on purpose:
a non-assessable or sensitive skill still says what an item is about, even
though no evidence is recorded against it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pensum.items.schema import QuizItem
from pensum.skills.schema import SkillFile, Strand

# Fewer than two questions is a single question, not a drill.
MIN_ITEMS = 2


@dataclass(frozen=True)
class Topic:
    """One strand a checkpoint can be drilled on, and how many questions it has."""

    strand: Strand
    count: int


def strands_of(item: QuizItem, checkpoint: int, skill_file: SkillFile) -> set[str]:
    """The strands an item belongs to: its named skill's, else its goal's skills'."""
    if item.skill is not None:
        named = skill_file.skill(item.skill)
        return {named.strand} if named is not None else set()
    return {
        skill.strand
        for skill in skill_file.skills
        if skill.checkpoint == checkpoint and item.goal in skill.refs
    }


def topics(pool: list[QuizItem], checkpoint: int, skill_file: SkillFile) -> tuple[Topic, ...]:
    """The strands with enough questions to drill, in the skills file's order."""
    counts: dict[str, int] = {}
    for item in pool:
        for strand in strands_of(item, checkpoint, skill_file):
            counts[strand] = counts.get(strand, 0) + 1
    return tuple(
        Topic(strand=strand, count=counts[strand.id])
        for strand in skill_file.strands
        if counts.get(strand.id, 0) >= MIN_ITEMS
    )


def in_topic(
    pool: list[QuizItem], strand: str, checkpoint: int, skill_file: SkillFile
) -> list[QuizItem]:
    """The part of a pool that belongs to one strand."""
    return [item for item in pool if strand in strands_of(item, checkpoint, skill_file)]
