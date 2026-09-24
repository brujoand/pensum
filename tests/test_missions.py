"""The missions validator, rule by rule, and the cards the missions print.

Each rule gets a file that breaks it and nothing else, against a skills file
small enough to read: one skill the quiz checks and one it does not.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml

from pensum.i18n import catalog
from pensum.missions.cards import CARDS
from pensum.missions.schema import CardKind
from pensum.missions.validate import validate
from pensum.skills.loader import SkillLibrary
from pensum.skills.schema import SkillFile

STATIC = Path(__file__).resolve().parents[1] / "src" / "pensum" / "web" / "static"


def _skill(skill_id: str, *, assessable: bool) -> dict[str, Any]:
    return {
        "id": skill_id,
        "strand": skill_id.split(".")[1],
        "checkpoint": 2,
        "refs": ["KM1"],
        "i_can": {"nob": "Jeg kan telle.", "eng": "I can count."},
        "teacher": {"nob": "Teller.", "eng": "Counts."},
        "stages": ["concrete"],
        "assessable": assessable,
        "reviewed": False,
    }


@pytest.fixture
def skills() -> SkillLibrary:
    return SkillLibrary(
        [
            SkillFile.model_validate(
                {
                    "subject": "MAT01-06",
                    "strands": [{"id": "counting", "title": {"nob": "Telling", "eng": "Counting"}}],
                    "skills": [
                        _skill("mat.counting.on-screen", assessable=True),
                        _skill("mat.counting.off-screen", assessable=False),
                    ],
                }
            )
        ]
    )


def _mission(mission_id: str = "mat.count-shoes", **overrides: Any) -> dict[str, Any]:
    mission = {
        "id": mission_id,
        "skill": "mat.counting.off-screen",
        "title": {"nob": "Tell sko", "eng": "Count shoes"},
        "steps": [
            {"nob": "Tell skoene.", "eng": "Count the shoes."},
            {"nob": "Skriv tallet.", "eng": "Write the number."},
        ],
        "confirm": "self",
        "reviewed": False,
    }
    mission.update(overrides)
    return mission


VALID: dict[str, Any] = {"subject": "MAT01-06", "missions": [_mission()]}


@pytest.fixture
def data() -> dict[str, Any]:
    return copy.deepcopy(VALID)


def _run(tmp_path: Path, skills: SkillLibrary, data: dict[str, Any], name: str = "") -> str:
    path = tmp_path / f"{name or data['subject']}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return "\n".join(validate(tmp_path, skills))


def test_a_valid_file_has_no_problems(tmp_path: Path, skills: SkillLibrary, data) -> None:
    assert _run(tmp_path, skills, data) == ""


def test_no_missions_is_not_an_error(tmp_path: Path, skills: SkillLibrary) -> None:
    assert validate(tmp_path, skills) == []


# Rule 1 ----------------------------------------------------------------------


def test_rule_1_the_skill_must_exist(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["skill"] = "mat.counting.renamed"
    assert "skill mat.counting.renamed is not in MAT01-06" in _run(tmp_path, skills, data)


def test_rule_1_the_subject_must_have_skills(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["subject"] = "NOR01-08"
    data["missions"][0]["id"] = "nor.count-shoes"
    assert "NOR01-08 has no skills file" in _run(tmp_path, skills, data)


# Rule 2 ----------------------------------------------------------------------


def test_rule_2_the_skill_must_be_off_screen(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["skill"] = "mat.counting.on-screen"
    assert "is assessable on screen" in _run(tmp_path, skills, data)


# Rule 3 ----------------------------------------------------------------------


def test_rule_3_one_step_is_too_few(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["steps"] = data["missions"][0]["steps"][:1]
    assert "has 1 step(s); a mission has 2 to 5" in _run(tmp_path, skills, data)


def test_rule_3_six_steps_is_too_many(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["steps"] = data["missions"][0]["steps"] * 3
    assert "has 6 step(s)" in _run(tmp_path, skills, data)


def test_rule_3_five_steps_is_fine(tmp_path: Path, skills: SkillLibrary, data) -> None:
    step = data["missions"][0]["steps"][0]
    data["missions"][0]["steps"] = [step] * 5
    assert _run(tmp_path, skills, data) == ""


# Rule 4 ----------------------------------------------------------------------


def test_rule_4_a_question_card_needs_a_question(
    tmp_path: Path, skills: SkillLibrary, data
) -> None:
    data["missions"][0]["card"] = "question"
    assert "a question card needs a question" in _run(tmp_path, skills, data)


def test_rule_4_a_question_needs_a_question_card(
    tmp_path: Path, skills: SkillLibrary, data
) -> None:
    data["missions"][0]["question"] = {"nob": "Hva er et tall?", "eng": "What is a number?"}
    assert "has a question but no question card" in _run(tmp_path, skills, data)


def test_rule_4_a_question_card_with_its_question(
    tmp_path: Path, skills: SkillLibrary, data
) -> None:
    data["missions"][0]["card"] = "question"
    data["missions"][0]["question"] = {"nob": "Hva er et tall?", "eng": "What is a number?"}
    assert _run(tmp_path, skills, data) == ""


# Rule 5 ----------------------------------------------------------------------


def test_rule_5_ids_are_unique(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"].append(_mission())
    assert "mat.count-shoes: mission id is defined 2 times" in _run(tmp_path, skills, data)


def test_rule_5_ids_start_with_the_subject_prefix(
    tmp_path: Path, skills: SkillLibrary, data
) -> None:
    data["missions"][0]["id"] = "nor.count-shoes"
    assert "id must start with mat." in _run(tmp_path, skills, data)


def test_rule_5_the_card_kind_is_from_the_fixed_set(
    tmp_path: Path, skills: SkillLibrary, data
) -> None:
    data["missions"][0]["card"] = "poster"
    assert "card" in _run(tmp_path, skills, data)


def test_rule_5_both_languages_are_present(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["steps"][1] = {"nob": "Skriv tallet."}
    assert "steps.1.eng" in _run(tmp_path, skills, data)


def test_rule_5_confirm_is_teacher_or_self(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["confirm"] = "parent"
    assert "confirm" in _run(tmp_path, skills, data)


def test_unknown_keys_are_refused(tmp_path: Path, skills: SkillLibrary, data) -> None:
    data["missions"][0]["photo"] = True
    assert "photo" in _run(tmp_path, skills, data)


def test_the_file_is_named_for_its_subject(tmp_path: Path, skills: SkillLibrary, data) -> None:
    assert "the file is named for it" in _run(tmp_path, skills, data, name="NOR01-08")


def test_broken_yaml_is_reported_not_raised(tmp_path: Path, skills: SkillLibrary) -> None:
    (tmp_path / "MAT01-06.yaml").write_text("missions: [unclosed", encoding="utf-8")
    assert validate(tmp_path, skills)


# The cards -------------------------------------------------------------------


def test_every_card_kind_has_a_card_and_no_more() -> None:
    """A kind with no card is a page that fails on the one mission naming it."""
    assert set(CARDS) == set(get_args(CardKind))


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_every_card_line_has_text_in_both_locales(locale: str) -> None:
    """A card whose shape outgrew its words would print a key name."""
    strings = catalog(locale)
    missing = [key for card in CARDS.values() for key in card.keys if not strings.get(key)]
    assert missing == []


@pytest.mark.parametrize("locale", ["nb", "en"])
def test_no_card_has_words_its_shape_does_not_print(locale: str) -> None:
    """And a card whose shape shrank would silently drop its last line."""
    printed = {key for card in CARDS.values() for key in card.keys}
    authored = {key for key in catalog(locale) if key.startswith("missions.card.")}
    assert authored - printed == set()


def test_the_script_never_sends_anything() -> None:
    """Ticks stay in the browser; the file has no way to send them."""
    source = (STATIC / "missions.js").read_text(encoding="utf-8")
    for call in ("fetch", "XMLHttpRequest", "sendBeacon", "WebSocket", "htmx"):
        assert not re.search(rf"\b{call}\b", source), call
