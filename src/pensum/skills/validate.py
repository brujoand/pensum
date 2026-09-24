"""Validate skills files against the curriculum catalogue.

Runs as a pre-commit hook and in CI, offline, in the style of
`pensum.items.validate`. The rules exist because every one of their failures is
silent on the page that shows skills:

1. Every goal in the subject is cited by some skill. A goal nobody read is a
   hole in the progression guide that looks like a finished page.
2. Every cited goal exists, at the skill's own checkpoint. A curriculum revision
   renumbers every code, and a skill citing a goal from another checkpoint puts
   Udir's words in the wrong column.
3. `needs` points at skills in the same file, and never in a circle. A cycle is
   a pair of skills each waiting for the other.
4. `i_can` is at most twelve words, so it can be read aloud to a seven-year-old.
5. Ids are unique, strands referenced exist, and the per-field rules in
   `schema.py` hold (stages valid and ordered, both languages present).
6. A sensitive skill says so with `sensitive: true`, never with a comment. The
   comment was the first convention, and the code cannot read it: a skill marked
   only that way would grow a plant on the pupil's map and appear on the class
   grid.

A subject without a file is fine. A file that exists must pass all six.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.domain.models import Subject
from pensum.skills.loader import DEFAULT_SKILLS_DIR, read
from pensum.skills.schema import PREFIXES, SkillFile

MAX_I_CAN_WORDS = 12

# The old way of marking a sensitive skill: a YAML comment above it.
SENSITIVE_COMMENT = re.compile(r"^\s*#\s*sensitive\b", re.IGNORECASE | re.MULTILINE)


def validate(skills_dir: Path | None = None, catalogue: Catalogue | None = None) -> list[str]:
    """Return a problem per line. Empty means everything checks out."""
    directory = skills_dir or DEFAULT_SKILLS_DIR
    catalogue = catalogue or Catalogue.load()
    problems: list[str] = []
    files: list[SkillFile] = []

    for path in sorted(directory.glob("*.yaml")):
        where = path.name
        try:
            skill_file = read(path)
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{where}: {exc}")
            continue
        if skill_file.subject != path.stem:
            problems.append(
                f"{where}: declares subject {skill_file.subject}; the file is named for it"
            )
            continue
        subject = catalogue.subject(skill_file.subject)
        if subject is None:
            problems.append(f"{where}: unknown subject {skill_file.subject}")
            continue
        files.append(skill_file)
        problems.extend(check(skill_file, subject))
        if SENSITIVE_COMMENT.search(path.read_text(encoding="utf-8")):
            problems.append(
                f"{where}: marks a skill sensitive with a comment; "
                "use `sensitive: true` on the skill, which the code can read"
            )

    # Ids are globally unique, not only within a file: they are what evidence
    # and mastery will be filed under, across every subject a pupil takes.
    # Counted once per file, so a duplicate inside one file is reported by
    # `check` alone rather than twice.
    files_using = Counter(skill_id for f in files for skill_id in {s.id for s in f.skills})
    for skill_id, count in sorted(files_using.items()):
        if count > 1:
            problems.append(f"{skill_id}: id is used in {count} skills files")

    return problems


def check(skill_file: SkillFile, subject: Subject) -> list[str]:
    """Every rule that needs more than one field, for one subject's file."""
    return [
        *_identity_problems(skill_file, subject),
        *_ref_problems(skill_file, subject),
        *_coverage_problems(skill_file, subject),
        *_needs_problems(skill_file),
        *_i_can_problems(skill_file),
    ]


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, n in Counter(values).items() if n > 1)


def _identity_problems(skill_file: SkillFile, subject: Subject) -> list[str]:
    """Rule 5: unique ids, and each skill filed under a strand that exists."""
    problems: list[str] = []
    code = subject.code
    for strand_id in _duplicates([s.id for s in skill_file.strands]):
        problems.append(f"{code}: strand id {strand_id} is defined more than once")
    for skill_id in _duplicates([s.id for s in skill_file.skills]):
        problems.append(f"{skill_id}: skill id is defined more than once")

    prefix = PREFIXES.get(code)
    if prefix is None:
        problems.append(f"{code}: no skill id prefix is registered for this subject")

    strand_ids = {s.id for s in skill_file.strands}
    for skill in skill_file.skills:
        if skill.strand not in strand_ids:
            problems.append(f"{skill.id}: strand {skill.strand} is not defined in this file")
        expected = f"{prefix}.{skill.strand}."
        if prefix is not None and not skill.id.startswith(expected):
            problems.append(f"{skill.id}: id must start with {expected}")
    return problems


def _ref_problems(skill_file: SkillFile, subject: Subject) -> list[str]:
    """Rule 2: each ref is a goal of this subject, at the skill's checkpoint."""
    after_year = {
        goal.code: goal_set.after_year for goal_set in subject.goal_sets for goal in goal_set.goals
    }
    problems: list[str] = []
    for skill in skill_file.skills:
        for ref in skill.refs:
            if ref not in after_year:
                problems.append(
                    f"{skill.id}: ref {ref} is not a goal of {subject.code}; "
                    "it may have been renumbered by a curriculum revision"
                )
            elif after_year[ref] != skill.checkpoint:
                problems.append(
                    f"{skill.id}: ref {ref} belongs to the checkpoint after "
                    f"{after_year[ref]}. trinn, not {skill.checkpoint}"
                )
    return problems


def _coverage_problems(skill_file: SkillFile, subject: Subject) -> list[str]:
    """Rule 1: no goal of the subject goes uncited."""
    cited = {ref for skill in skill_file.skills for ref in skill.refs}
    missing = sorted(
        goal.code
        for goal_set in subject.goal_sets
        for goal in goal_set.goals
        if goal.code not in cited
    )
    if not missing:
        return []
    return [f"{subject.code}: {len(missing)} goal(s) cited by no skill: {', '.join(missing)}"]


def _needs_problems(skill_file: SkillFile) -> list[str]:
    """Rule 3: every `needs` resolves within the file, and the graph is acyclic."""
    ids = {skill.id for skill in skill_file.skills}
    problems = [
        f"{skill.id}: needs {need}, which is not a skill in this file"
        for skill in skill_file.skills
        for need in skill.needs
        if need not in ids
    ]
    graph = {skill.id: [n for n in skill.needs if n in ids] for skill in skill_file.skills}

    # Depth-first, colouring nodes as they are entered and left. Meeting a node
    # that is still being entered is a cycle, and the path back to it is what
    # the author needs to see to break it.
    done: set[str] = set()
    path: list[str] = []
    reported: set[frozenset[str]] = set()

    def visit(node: str) -> None:
        if node in done:
            return
        if node in path:
            cycle = path[path.index(node) :]
            key = frozenset(cycle)
            if key not in reported:
                reported.add(key)
                problems.append(f"needs form a cycle: {' -> '.join([*cycle, node])}")
            return
        path.append(node)
        for need in graph[node]:
            visit(need)
        path.pop()
        done.add(node)

    for node in sorted(graph):
        visit(node)
    return problems


def _i_can_problems(skill_file: SkillFile) -> list[str]:
    """Rule 4: short enough to read aloud to a young child."""
    problems: list[str] = []
    for skill in skill_file.skills:
        for language in ("nob", "eng"):
            words = len(getattr(skill.i_can, language).split())
            if words > MAX_I_CAN_WORDS:
                problems.append(
                    f"{skill.id}: i_can.{language} is {words} words; the limit is {MAX_I_CAN_WORDS}"
                )
    return problems


def main() -> int:
    problems = validate()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s) found in skills files.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
