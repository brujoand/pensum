"""Loading missions files from disk.

As with skills, a subject with no file is an ordinary state: missions are
authored subject by subject, and the pages that show them appear where a file
exists.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pensum.missions.schema import Mission, MissionFile

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MISSIONS_DIR = REPO_ROOT / "data" / "missions"


def read(path: Path) -> MissionFile:
    """Parse one file. Raises on YAML or schema errors; the validator reports them."""
    return MissionFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class MissionLibrary:
    """Every subject's missions file, indexed by subject, mission and skill."""

    def __init__(self, files: list[MissionFile]) -> None:
        self._by_subject = {f.subject: f for f in files}
        self._by_id = {m.id: (f.subject, m) for f in files for m in f.missions}
        by_skill: dict[str, list[Mission]] = {}
        for f in files:
            for mission in f.missions:
                by_skill.setdefault(mission.skill, []).append(mission)
        self._by_skill = {skill: tuple(missions) for skill, missions in by_skill.items()}

    @classmethod
    def load(cls, missions_dir: Path | None = None) -> MissionLibrary:
        directory = missions_dir or DEFAULT_MISSIONS_DIR
        return cls([read(path) for path in sorted(directory.glob("*.yaml"))])

    def for_subject(self, subject_code: str) -> MissionFile | None:
        return self._by_subject.get(subject_code)

    def mission(self, mission_id: str) -> tuple[str, Mission] | None:
        """The mission and the subject it belongs to, or None."""
        return self._by_id.get(mission_id)

    def for_skill(self, skill_id: str) -> tuple[Mission, ...]:
        return self._by_skill.get(skill_id, ())

    def by_skill(self, subject_code: str) -> dict[str, tuple[Mission, ...]]:
        """Each skill of one subject that has missions, with them in file order."""
        mission_file = self.for_subject(subject_code)
        if mission_file is None:
            return {}
        return {m.skill: self.for_skill(m.skill) for m in mission_file.missions}
