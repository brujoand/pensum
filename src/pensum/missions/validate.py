"""Validate missions files against the skills they serve.

Runs as a pre-commit hook and in CI, offline, in the style of
`pensum.skills.validate`. Every rule is here because its failure is silent on
the page:

1. The skill exists, in this subject's skills file. A renamed skill would
   otherwise leave its missions on no progression page at all.
2. The skill is `assessable: false`. A mission for a skill the quiz already
   checks is a second, unrecorded route to the same thing, and says the screen
   cannot check what it does.
3. Two to five steps. One step is not a checklist, and six is a worksheet.
4. A question card carries its question, and no other card carries one. A
   question card with nothing to print is a blank sheet of paper.
5. Ids are unique across every file and start with the subject's prefix, and
   the per-field rules in `schema.py` hold (both languages present, a card kind
   from the fixed set, `confirm` either teacher or self).

The skills files are taken as valid here; `pensum.skills.validate` is their
gate. A subject without a missions file is fine.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml
from pydantic import ValidationError

from pensum.missions.loader import DEFAULT_MISSIONS_DIR, read
from pensum.missions.schema import MissionFile
from pensum.skills.loader import SkillLibrary
from pensum.skills.schema import PREFIXES, SkillFile

MIN_STEPS = 2
MAX_STEPS = 5


def validate(missions_dir: Path | None = None, skills: SkillLibrary | None = None) -> list[str]:
    """Return a problem per line. Empty means everything checks out."""
    directory = missions_dir or DEFAULT_MISSIONS_DIR
    if skills is None:
        try:
            skills = SkillLibrary.load()
        except (ValidationError, yaml.YAMLError) as exc:
            return [f"the skills files do not load, so missions cannot be checked: {exc}"]
    problems: list[str] = []
    files: list[MissionFile] = []

    for path in sorted(directory.glob("*.yaml")):
        where = path.name
        try:
            mission_file = read(path)
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{where}: {exc}")
            continue
        if mission_file.subject != path.stem:
            problems.append(
                f"{where}: declares subject {mission_file.subject}; the file is named for it"
            )
            continue
        skill_file = skills.for_subject(mission_file.subject)
        if skill_file is None:
            problems.append(f"{where}: {mission_file.subject} has no skills file to serve")
            continue
        files.append(mission_file)
        problems.extend(check(mission_file, skill_file))

    # Rule 5, across files: a mission id is its page's address, and two missions
    # at one address would show whichever loaded last.
    ids = Counter(m.id for f in files for m in f.missions)
    for mission_id, count in sorted(ids.items()):
        if count > 1:
            problems.append(f"{mission_id}: mission id is defined {count} times")
    return problems


def check(mission_file: MissionFile, skill_file: SkillFile) -> list[str]:
    """Every rule that needs more than one field, for one subject's file."""
    problems: list[str] = []
    prefix = PREFIXES.get(mission_file.subject)
    for mission in mission_file.missions:
        where = mission.id
        if prefix is not None and not mission.id.startswith(f"{prefix}."):
            problems.append(f"{where}: id must start with {prefix}.")

        skill = skill_file.skill(mission.skill)
        if skill is None:
            problems.append(f"{where}: skill {mission.skill} is not in {skill_file.subject}")
        elif skill.assessable:
            problems.append(
                f"{where}: skill {mission.skill} is assessable on screen; "
                "missions serve only skills marked assessable: false"
            )

        count = len(mission.steps)
        if not MIN_STEPS <= count <= MAX_STEPS:
            problems.append(
                f"{where}: has {count} step(s); a mission has {MIN_STEPS} to {MAX_STEPS}"
            )

        if mission.card == "question" and mission.question is None:
            problems.append(f"{where}: a question card needs a question to print")
        if mission.card != "question" and mission.question is not None:
            problems.append(f"{where}: has a question but no question card to print it on")
    return problems


def main() -> int:
    problems = validate()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s) found in missions files.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
