"""The skills validator, rule by rule, against a curriculum small enough to read.

Every rule gets a file that breaks it and nothing else, so a test failing here
names the rule that stopped holding. The fixture subject has three goals over two
checkpoints: enough for coverage, checkpoint mismatches and a `needs` chain.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pensum.catalogue.loader import Catalogue
from pensum.domain.models import Subject
from pensum.skills.schema import SkillFile, SkillText
from pensum.skills.validate import validate


def _subject(code: str, goals: dict[int, list[str]]) -> Subject:
    return Subject.model_validate(
        {
            "code": code,
            "title": {"by_language": {"nob": code}},
            "goal_sets": [
                {
                    "code": f"{code}-{year}",
                    "title": {"by_language": {"nob": f"etter {year}. trinn"}},
                    "after_year": year,
                    "applies_to_years": [year],
                    "goals": [
                        {"code": goal, "text": {"by_language": {"nob": f"mål {goal}"}}}
                        for goal in codes
                    ],
                }
                for year, codes in goals.items()
            ],
        }
    )


@pytest.fixture
def catalogue() -> Catalogue:
    return Catalogue(
        [
            _subject("MAT01-06", {2: ["KM1", "KM2"], 4: ["KM3"]}),
            _subject("NOR01-08", {2: ["KM9"]}),
        ]
    )


def _skill(skill_id: str, checkpoint: int, refs: list[str], needs: list[str]) -> dict[str, Any]:
    return {
        "id": skill_id,
        "strand": skill_id.split(".")[1],
        "checkpoint": checkpoint,
        "refs": refs,
        "needs": needs,
        "i_can": {"nob": "Jeg kan telle til ti.", "eng": "I can count to ten."},
        "teacher": {
            "nob": "Teller ti klosser. Ikke ennå: teller én to ganger.",
            "eng": "Counts ten blocks. Not yet: counts one twice.",
        },
        "stages": ["concrete", "pictorial", "abstract"],
        "misconceptions": ["counts-object-twice"],
        "assessable": True,
    }


VALID: dict[str, Any] = {
    "subject": "MAT01-06",
    "strands": [{"id": "counting", "title": {"nob": "Telling", "eng": "Counting"}}],
    "skills": [
        _skill("mat.counting.to-ten", 2, ["KM1", "KM2"], []),
        _skill("mat.counting.to-hundred", 4, ["KM3"], ["mat.counting.to-ten"]),
    ],
}


def _run(tmp_path: Path, catalogue: Catalogue, data: dict[str, Any], name: str = "") -> list[str]:
    path = tmp_path / f"{name or data['subject']}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return validate(tmp_path, catalogue)


@pytest.fixture
def data() -> dict[str, Any]:
    return copy.deepcopy(VALID)


def _joined(problems: list[str]) -> str:
    return "\n".join(problems)


def test_a_valid_file_has_no_problems(tmp_path: Path, catalogue: Catalogue, data) -> None:
    assert _run(tmp_path, catalogue, data) == []


def test_a_subject_without_a_file_is_not_an_error(tmp_path: Path, catalogue: Catalogue) -> None:
    assert validate(tmp_path, catalogue) == []


# Rule 1 ----------------------------------------------------------------------


def test_rule_1_every_goal_is_cited(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][0]["refs"] = ["KM1"]
    problems = _run(tmp_path, catalogue, data)
    assert "1 goal(s) cited by no skill: KM2" in _joined(problems)


# Rule 2 ----------------------------------------------------------------------


def test_rule_2_a_ref_must_exist(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][0]["refs"] = ["KM1", "KM2", "KM404"]
    problems = _run(tmp_path, catalogue, data)
    assert "ref KM404 is not a goal of MAT01-06" in _joined(problems)


def test_rule_2_a_ref_must_be_from_another_subject_either(
    tmp_path: Path, catalogue: Catalogue, data
) -> None:
    data["skills"][0]["refs"] = ["KM1", "KM2", "KM9"]
    assert "ref KM9 is not a goal of MAT01-06" in _joined(_run(tmp_path, catalogue, data))


def test_rule_2_a_ref_must_match_the_checkpoint(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][1]["refs"] = ["KM3", "KM2"]
    problems = _run(tmp_path, catalogue, data)
    assert "ref KM2 belongs to the checkpoint after 2. trinn, not 4" in _joined(problems)


def test_rule_2_at_least_one_ref(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][1]["refs"] = []
    assert "refs" in _joined(_run(tmp_path, catalogue, data))


# Rule 3 ----------------------------------------------------------------------


def test_rule_3_needs_must_exist_in_the_file(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][1]["needs"] = ["nor.reading.letters"]
    problems = _run(tmp_path, catalogue, data)
    assert "needs nor.reading.letters, which is not a skill in this file" in _joined(problems)


def test_rule_3_needs_must_not_cycle(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][0]["needs"] = ["mat.counting.to-hundred"]
    problems = _run(tmp_path, catalogue, data)
    assert len([p for p in problems if "cycle" in p]) == 1
    assert "mat.counting.to-hundred -> mat.counting.to-ten" in _joined(problems)


def test_rule_3_a_skill_cannot_need_itself(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][0]["needs"] = ["mat.counting.to-ten"]
    assert "cycle" in _joined(_run(tmp_path, catalogue, data))


# Rule 4 ----------------------------------------------------------------------


def test_rule_4_i_can_is_at_most_twelve_words(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][0]["i_can"]["eng"] = " ".join(["word"] * 13)
    problems = _run(tmp_path, catalogue, data)
    assert "i_can.eng is 13 words; the limit is 12" in _joined(problems)


def test_rule_4_twelve_words_is_fine(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][0]["i_can"]["nob"] = " ".join(["ord"] * 12)
    assert _run(tmp_path, catalogue, data) == []


# Rule 5 ----------------------------------------------------------------------


def test_rule_5_skill_ids_are_unique(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"].append(copy.deepcopy(data["skills"][0]))
    problems = _run(tmp_path, catalogue, data)
    assert "mat.counting.to-ten: skill id is defined more than once" in _joined(problems)


def test_rule_5_strand_ids_are_unique(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["strands"].append(copy.deepcopy(data["strands"][0]))
    assert "strand id counting is defined more than once" in _joined(
        _run(tmp_path, catalogue, data)
    )


def test_rule_5_ids_are_unique_across_files(tmp_path: Path, catalogue: Catalogue, data) -> None:
    other = copy.deepcopy(data)
    other["subject"] = "NOR01-08"
    other["skills"] = [_skill("mat.counting.to-ten", 2, ["KM9"], [])]
    _run(tmp_path, catalogue, other)
    problems = _run(tmp_path, catalogue, data)
    assert "mat.counting.to-ten: id is used in 2 skills files" in _joined(problems)


def test_rule_5_the_strand_must_exist(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][1]["id"] = "mat.shapes.to-hundred"
    data["skills"][1]["strand"] = "shapes"
    problems = _run(tmp_path, catalogue, data)
    assert "strand shapes is not defined in this file" in _joined(problems)


def test_rule_5_the_id_names_subject_and_strand(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["skills"][1]["id"] = "nor.counting.to-hundred"
    data["skills"][1]["needs"] = []
    problems = _run(tmp_path, catalogue, data)
    assert "nor.counting.to-hundred: id must start with mat.counting." in _joined(problems)


@pytest.mark.parametrize(
    "stages",
    [["abstract", "concrete"], ["concrete", "concrete"], [], ["symbolic"]],
)
def test_rule_5_stages_are_valid_and_ordered(
    tmp_path: Path, catalogue: Catalogue, data, stages: list[str]
) -> None:
    data["skills"][0]["stages"] = stages
    problems = _run(tmp_path, catalogue, data)
    assert len(problems) == 1
    assert "stages" in problems[0]


@pytest.mark.parametrize("value", ["", "   ", None])
def test_rule_5_both_languages_are_present(
    tmp_path: Path, catalogue: Catalogue, data, value: str | None
) -> None:
    if value is None:
        del data["skills"][0]["teacher"]["eng"]
    else:
        data["skills"][0]["teacher"]["eng"] = value
    problems = _run(tmp_path, catalogue, data)
    assert len(problems) == 1
    assert "teacher.eng" in problems[0]


def test_rule_5_strand_titles_need_both_languages(
    tmp_path: Path, catalogue: Catalogue, data
) -> None:
    data["strands"][0]["title"] = {"nob": "Telling"}
    assert "eng" in _joined(_run(tmp_path, catalogue, data))


# The contract ----------------------------------------------------------------


def test_unknown_keys_are_refused(tmp_path: Path, catalogue: Catalogue, data) -> None:
    """The format is shared by several authors; a misspelt key must not vanish."""
    data["skills"][0]["refrences"] = ["KM1"]
    assert "refrences" in _joined(_run(tmp_path, catalogue, data))


def test_the_file_is_named_for_its_subject(tmp_path: Path, catalogue: Catalogue, data) -> None:
    problems = _run(tmp_path, catalogue, data, name="MAT01-05")
    assert "declares subject MAT01-06" in _joined(problems)


def test_an_unknown_subject_is_reported(tmp_path: Path, catalogue: Catalogue, data) -> None:
    data["subject"] = "XYZ01-01"
    assert "unknown subject XYZ01-01" in _joined(_run(tmp_path, catalogue, data))


def test_broken_yaml_is_reported_not_raised(tmp_path: Path, catalogue: Catalogue) -> None:
    (tmp_path / "MAT01-06.yaml").write_text("subject: [unclosed\n", encoding="utf-8")
    assert len(validate(tmp_path, catalogue)) == 1


def test_skill_text_follows_the_ui_locale() -> None:
    text = SkillText(nob="Hei", eng="Hello")
    assert text.get("en") == "Hello"
    assert text.get("nb") == "Hei"
    # Nynorsk readers get the bokmål chrome, and so our text in bokmål too.
    assert text.get("nn") == "Hei"


def test_a_skill_file_needs_at_least_one_skill() -> None:
    with pytest.raises(ValidationError):
        SkillFile.model_validate({**VALID, "skills": []})
