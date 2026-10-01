"""Fact packs and instruction sets: the schema, the validator, and the review gate.

Nothing here calls a model. These are the rules a pack has to meet before one
is ever prompted from it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from review_helpers import approve_all, decision, ledger_at

from pensum.catalogue.loader import Catalogue
from pensum.drills.loader import DrillLibrary
from pensum.drills.schema import MAX_QUESTIONS, FactPack, InstructionSet, PackFile
from pensum.drills.validate import validate
from pensum.review.content import REVIEW_KEYS

SUBJECT = "SAF01-05"
GOAL_SET = "KV1150"
GOAL = "KM14695"
PACK_ID = "saf-kv1150-test"


def fact(number: int) -> dict[str, str]:
    return {"id": f"f{number}", "nb": f"Faktum {number}.", "en": f"Fact {number}."}


def pack(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": PACK_ID,
        "goal": GOAL,
        "difficulty": 2,
        "title": {"nb": "Prøvepakke", "en": "Test pack"},
        "instructions": "recall",
        "questions": 2,
        "facts": [fact(1), fact(2), fact(3)],
    }
    return base | overrides


def instructions(**overrides: object) -> dict[str, object]:
    return {"id": "recall", "distractors": 3, "rules": "Ask what the fact states."} | overrides


def write(
    directory: Path,
    packs: list[dict[str, object]] | None = None,
    *,
    subject: str = SUBJECT,
    goal_set: str = GOAL_SET,
    instruction_sets: list[dict[str, object]] | None = None,
) -> Path:
    """A drills directory with one pack file and its instruction sets."""
    pack_dir = directory / subject
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / f"{goal_set}.yaml").write_text(
        yaml.safe_dump(
            {"subject": subject, "goal_set": goal_set, "packs": packs or [pack()]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    instructions_dir = directory / "instructions"
    instructions_dir.mkdir(exist_ok=True)
    for instruction_set in instruction_sets if instruction_sets is not None else [instructions()]:
        (instructions_dir / f"{instruction_set['id']}.yaml").write_text(
            yaml.safe_dump(instruction_set), encoding="utf-8"
        )
    return directory


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return Catalogue.load()


# --- schema -----------------------------------------------------------------


def test_a_pack_loads_and_finds_a_fact_by_id() -> None:
    loaded = FactPack.model_validate(pack())
    found = loaded.fact("f2")
    assert found is not None
    assert found.get("nb") == "Faktum 2."
    assert found.get("en") == "Fact 2."
    assert loaded.fact("f9") is None


def test_a_pack_needs_a_fact_per_question() -> None:
    with pytest.raises(ValidationError, match="at least one fact per question"):
        FactPack.model_validate(pack(questions=4))


def test_fact_ids_are_unique_within_a_pack() -> None:
    with pytest.raises(ValidationError, match="fact ids must be unique"):
        FactPack.model_validate(pack(facts=[fact(1), fact(1), fact(2)]))


def test_a_fact_is_one_line() -> None:
    paragraph = {"id": "f1", "nb": "Første setning.\nAndre setning.", "en": "One. Two."}
    with pytest.raises(ValidationError, match="one sentence, on one line"):
        FactPack.model_validate(pack(facts=[paragraph, fact(2)]))


def test_a_fact_needs_both_languages() -> None:
    with pytest.raises(ValidationError):
        FactPack.model_validate(pack(facts=[{"id": "f1", "nb": "Bare norsk."}, fact(2)]))


@pytest.mark.parametrize("fact_id", ["1", "f0", "fact-1", "F1"])
def test_a_fact_id_is_f_and_a_number(fact_id: str) -> None:
    with pytest.raises(ValidationError):
        FactPack.model_validate(pack(facts=[{**fact(1), "id": fact_id}, fact(2)]))


def test_a_pack_cannot_ask_for_more_than_a_short_drill() -> None:
    facts = [fact(n) for n in range(1, MAX_QUESTIONS + 3)]
    with pytest.raises(ValidationError):
        FactPack.model_validate(pack(questions=MAX_QUESTIONS + 1, facts=facts))


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        FactPack.model_validate(pack(prompt="Write five questions."))


@pytest.mark.parametrize("key", REVIEW_KEYS)
def test_a_pack_cannot_say_it_has_been_reviewed(key: str) -> None:
    with pytest.raises(ValidationError, match="not a content field"):
        FactPack.model_validate(pack(**{key: True}))


@pytest.mark.parametrize("key", REVIEW_KEYS)
def test_an_instruction_set_cannot_say_it_has_been_reviewed(key: str) -> None:
    with pytest.raises(ValidationError, match="not a content field"):
        InstructionSet.model_validate(instructions(**{key: True}))


@pytest.mark.parametrize("count", [1, 5])
def test_distractors_keep_a_question_a_legal_multiple_choice(count: int) -> None:
    with pytest.raises(ValidationError):
        InstructionSet.model_validate(instructions(distractors=count))


def test_a_pack_file_needs_a_pack() -> None:
    with pytest.raises(ValidationError):
        PackFile.model_validate({"subject": SUBJECT, "goal_set": GOAL_SET, "packs": []})


# --- validator --------------------------------------------------------------


def test_a_well_formed_directory_validates(tmp_path: Path, catalogue: Catalogue) -> None:
    assert validate(write(tmp_path), catalogue) == []


def test_a_missing_directory_is_no_drills_and_no_problem(
    tmp_path: Path, catalogue: Catalogue
) -> None:
    assert validate(tmp_path / "absent", catalogue) == []
    library = DrillLibrary.load(tmp_path / "absent")
    assert library.files == ()
    assert library.instruction_sets == ()


def test_a_goal_outside_the_goal_set_is_reported(tmp_path: Path, catalogue: Catalogue) -> None:
    problems = validate(write(tmp_path, [pack(goal="KM00000")]), catalogue)
    assert len(problems) == 1
    assert "goal KM00000 is not in KV1150" in problems[0]


def test_an_unknown_goal_set_is_reported(tmp_path: Path, catalogue: Catalogue) -> None:
    problems = validate(write(tmp_path, goal_set="KV0000"), catalogue)
    assert len(problems) == 1
    assert "not a goal set of SAF01-05" in problems[0]


def test_an_unknown_subject_is_reported(tmp_path: Path, catalogue: Catalogue) -> None:
    problems = validate(write(tmp_path, subject="XXX01-01"), catalogue)
    assert len(problems) == 1
    assert "unknown subject XXX01-01" in problems[0]


def test_a_missing_instruction_set_is_reported(tmp_path: Path, catalogue: Catalogue) -> None:
    problems = validate(write(tmp_path, instruction_sets=[]), catalogue)
    assert len(problems) == 1
    assert "names instruction set recall, which is missing" in problems[0]


def test_a_pack_file_is_named_for_what_it_declares(tmp_path: Path, catalogue: Catalogue) -> None:
    write(tmp_path)
    (tmp_path / SUBJECT / f"{GOAL_SET}.yaml").rename(tmp_path / SUBJECT / "KV1151.yaml")
    problems = validate(tmp_path, catalogue)
    assert len(problems) == 1
    assert "the file is named for its subject and goal set" in problems[0]


def test_an_instruction_set_file_is_named_for_its_id(tmp_path: Path, catalogue: Catalogue) -> None:
    write(tmp_path)
    (tmp_path / "instructions" / "recall.yaml").rename(tmp_path / "instructions" / "other.yaml")
    problems = validate(tmp_path, catalogue)
    assert any("the file is named for it" in p for p in problems)
    # And the pack that named it has nothing to be quizzed by.
    assert any("which is missing" in p for p in problems)


def test_a_pack_id_defined_in_two_files_is_reported(tmp_path: Path, catalogue: Catalogue) -> None:
    write(tmp_path)
    write(tmp_path, [pack(goal="KM14677")], goal_set="KV1149")
    problems = validate(tmp_path, catalogue)
    assert problems == [f"{PACK_ID}: pack id is defined 2 times"]


def test_a_file_that_does_not_parse_is_reported_and_the_rest_still_checked(
    tmp_path: Path, catalogue: Catalogue
) -> None:
    write(tmp_path)
    (tmp_path / SUBJECT / "KV1149.yaml").write_text("subject: [unclosed", encoding="utf-8")
    problems = validate(tmp_path, catalogue)
    assert len(problems) == 1
    assert problems[0].startswith(f"{SUBJECT}/KV1149.yaml:")


def test_the_instructions_directory_is_not_read_as_a_subject(
    tmp_path: Path, catalogue: Catalogue
) -> None:
    library = DrillLibrary.load(write(tmp_path))
    assert [f.subject for f in library.files] == [SUBJECT]
    assert [i.id for i in library.instruction_sets] == ["recall"]


# --- the review gate --------------------------------------------------------


def test_with_no_ledger_nothing_is_published(tmp_path: Path) -> None:
    library = DrillLibrary.load(write(tmp_path / "drills"))
    found = library.pack(PACK_ID)
    assert found is not None
    assert not library.has_ledger
    assert library.review_state(PACK_ID) == "pending"
    assert library.instructions_state("recall") == "pending"
    assert not library.publishes(found[1])


def test_a_pack_is_published_only_with_its_instruction_set(tmp_path: Path) -> None:
    library = DrillLibrary.load(write(tmp_path / "drills"))
    ledger = ledger_at(tmp_path / "db.sqlite")
    library.with_ledger(ledger)
    found = library.pack(PACK_ID)
    assert found is not None
    _, loaded = found

    ledger.store.record(decision("pack", PACK_ID, library.fingerprint(PACK_ID)))
    ledger.reload()
    assert library.review_state(PACK_ID) == "approved"
    assert not library.publishes(loaded), "the rules it is quizzed by are still unread"

    ledger.store.record(
        decision("instructions", "recall", library.instructions_fingerprint("recall"))
    )
    ledger.reload()
    assert library.publishes(loaded)


def test_a_rejected_instruction_set_withholds_every_pack_that_names_it(tmp_path: Path) -> None:
    library = DrillLibrary.load(write(tmp_path / "drills"))
    ledger = ledger_at(tmp_path / "db.sqlite")
    assert approve_all(ledger, drills=library) == 2
    found = library.pack(PACK_ID)
    assert found is not None
    assert library.publishes(found[1])

    ledger.store.record(
        decision("instructions", "recall", library.instructions_fingerprint("recall"), "rejected")
    )
    ledger.reload()
    assert library.instructions_state("recall") == "rejected"
    assert not library.publishes(found[1])


def test_an_edited_fact_sends_the_pack_back_for_review(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path / "db.sqlite")
    before = DrillLibrary.load(write(tmp_path / "before"))
    approve_all(ledger, drills=before)

    edited = fact(1) | {"nb": "Et annet faktum."}
    after = DrillLibrary.load(write(tmp_path / "after", [pack(facts=[edited, fact(2), fact(3)])]))
    after.with_ledger(ledger)
    found = after.pack(PACK_ID)
    assert found is not None
    assert after.review_state(PACK_ID) == "changed"
    assert not after.publishes(found[1])
    # The instruction set was not edited, and its approval stands.
    assert after.instructions_state("recall") == "approved"


def test_a_pack_naming_no_loaded_instruction_set_is_not_published(tmp_path: Path) -> None:
    library = DrillLibrary.load(write(tmp_path / "drills", instruction_sets=[]))
    approve_all(ledger_at(tmp_path / "db.sqlite"), drills=library)
    found = library.pack(PACK_ID)
    assert found is not None
    assert library.review_state(PACK_ID) == "approved"
    assert not library.publishes(found[1])


def test_unknown_ids_are_pending_and_have_no_fingerprint(tmp_path: Path) -> None:
    library = DrillLibrary.load(write(tmp_path))
    assert library.pack("nope") is None
    assert library.instruction_set("nope") is None
    assert library.review_state("nope") == "pending"
    assert library.instructions_state("nope") == "pending"
    assert library.fingerprint("nope") is None
    assert library.instructions_fingerprint("nope") is None
