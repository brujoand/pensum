"""Validate drills files against the curriculum catalogue and each other.

Runs as a pre-commit hook and in CI, offline, in the style of
`pensum.items.validate`. Every rule is here because its failure is silent
later, when a model is prompted from the pack:

1. A pack file sits at `<subject>/<goal_set>.yaml` and says so itself, the
   subject and goal set exist, and each pack's goal is in that goal set. A
   curriculum revision that renumbers a goal orphans the pack otherwise.
2. A pack names an instruction set that exists. Without one there is nothing
   to prompt with, and the pack would never be offered.
3. An instruction set's file is named for its id.
4. Pack ids are unique across every file. A pack id is the key its questions
   are cached under.
5. The per-file rules in `schema.py` hold: both languages present, one fact
   per question at least, unique fact ids.

No model is involved here, and none of these rules judges whether a fact is
true. That is what review is for.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.drills.loader import (
    DEFAULT_DRILLS_DIR,
    instruction_paths,
    pack_paths,
    read_instructions,
    read_packs,
)
from pensum.drills.schema import PackFile


def validate(drills_dir: Path | None = None, catalogue: Catalogue | None = None) -> list[str]:
    """Return a problem per line. Empty means everything checks out."""
    directory = drills_dir or DEFAULT_DRILLS_DIR
    catalogue = catalogue if catalogue is not None else Catalogue.load()
    problems: list[str] = []

    instructions: set[str] = set()
    for path in instruction_paths(directory):
        where = path.relative_to(directory)
        try:
            instruction_set = read_instructions(path)
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{where}: {exc}")
            continue
        if instruction_set.id != path.stem:
            problems.append(f"{where}: declares id {instruction_set.id}; the file is named for it")
            continue
        instructions.add(instruction_set.id)

    files: list[PackFile] = []
    for path in pack_paths(directory):
        where = path.relative_to(directory)
        try:
            pack_file = read_packs(path)
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{where}: {exc}")
            continue
        if (pack_file.subject, pack_file.goal_set) != (path.parent.name, path.stem):
            problems.append(
                f"{where}: declares {pack_file.subject}/{pack_file.goal_set}; "
                "the file is named for its subject and goal set"
            )
            continue
        files.append(pack_file)
        problems.extend(check(pack_file, catalogue, instructions))

    ids = Counter(pack.id for f in files for pack in f.packs)
    for pack_id, count in sorted(ids.items()):
        if count > 1:
            problems.append(f"{pack_id}: pack id is defined {count} times")
    return problems


def check(pack_file: PackFile, catalogue: Catalogue, instructions: set[str]) -> list[str]:
    """Every rule that needs more than one file, for one goal set's packs."""
    subject = catalogue.subject(pack_file.subject)
    if subject is None:
        return [f"{pack_file.goal_set}: unknown subject {pack_file.subject}"]
    goal_set = subject.goal_set(pack_file.goal_set)
    if goal_set is None:
        return [
            f"{pack_file.goal_set}: not a goal set of {pack_file.subject}; "
            "the curriculum may have been revised"
        ]

    problems: list[str] = []
    known = {goal.code for goal in goal_set.goals}
    for pack in pack_file.packs:
        if pack.goal not in known:
            problems.append(
                f"{pack.id}: goal {pack.goal} is not in {pack_file.goal_set}; "
                "it may have been renumbered by a curriculum revision"
            )
        if pack.instructions not in instructions:
            problems.append(
                f"{pack.id}: names instruction set {pack.instructions}, which is missing"
            )
    return problems


def main() -> int:
    problems = validate()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s) found in drills files.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
