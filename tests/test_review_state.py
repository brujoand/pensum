"""Review state is data on the instance, and nowhere else.

The rules under test, each on its own:

* No content file can say whether it has been reviewed: the schemas refuse the
  old keys, and no committed file carries them.
* A decision carries a fingerprint of what was read, and applies only while the
  content still has it. An edit returns approved content to pending.
* A database from before fingerprints migrates, and its old rows approve
  nothing -- every instance starts pending.
* There is always a database, at a default path when none is configured.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from review_helpers import approve_all, decision, ledger_at

import pensum.config
from pensum.config import Settings
from pensum.items.loader import ItemBank
from pensum.items.schema import QuizItem
from pensum.items.sets import ItemSet
from pensum.items.template import ItemTemplate
from pensum.items.text import AuthoredText
from pensum.missions.schema import Mission
from pensum.reading.library import ReadingLibrary
from pensum.reading.schema import ReadingSet, ReadingText
from pensum.review.content import REVIEW_KEYS, fingerprint
from pensum.review.store import ReviewLedger, ReviewStore
from pensum.skills.schema import Skill
from pensum.writing.schema import WritingPrompt

REPO_ROOT = Path(__file__).resolve().parents[1]


def text(nb: str, en: str | None = None) -> AuthoredText:
    return AuthoredText(nb=nb, en=en or nb)


ITEM = {
    "id": "KM1-01",
    "goal": "KM1",
    "type": "numeric",
    "difficulty": 1,
    "prompt": {"nb": "Hva er 2 + 2?", "en": "What is 2 + 2?"},
    "explanation": {"nb": "2 + 2 = 4.", "en": "2 + 2 = 4."},
    "answer": 4,
}

TEMPLATE = {
    "id": "KM1-T1",
    "goal": "KM1",
    "difficulty": 2,
    "params": {"a": {"min": 2, "max": 4}},
    "answer": "a + 1",
    "prompt": {"nb": "Hva er {a} + 1?", "en": "What is {a} + 1?"},
    "explanation": {"nb": "Én mer enn {a}.", "en": "One more than {a}."},
}

READING = {
    "id": "tekst-1",
    "goal": "KM1",
    "language": "nb",
    "title": "Katten",
    "body": (
        "Katten min sover i sola hele dagen.\n"
        "Når det blir kveld, vil den ut og leke i hagen med meg.\n"
    ),
    "difficulty": 1,
    "source": "pensum",
}

WRITING = {
    "id": "skriv-1",
    "goal": "KM1",
    "language": "nb",
    "title": "Bokstaver",
    "kind": "letters",
    "text": "il",
    "difficulty": 1,
    "source": "pensum",
}

SKILL = {
    "id": "mat.counting.count-to-ten",
    "strand": "counting",
    "checkpoint": 2,
    "refs": ["KM1"],
    "i_can": {"nob": "Jeg kan telle til ti.", "eng": "I can count to ten."},
    "teacher": {"nob": "Teller til ti.", "eng": "Counts to ten."},
    "stages": ["concrete"],
    "assessable": True,
}

MISSION = {
    "id": "mat.count-steps",
    "skill": "mat.counting.count-to-ten",
    "title": {"nob": "Tell trinnene", "eng": "Count the steps"},
    "steps": [{"nob": "Tell.", "eng": "Count."}],
    "confirm": "self",
}

MODELS = [
    (QuizItem, ITEM),
    (ItemTemplate, TEMPLATE),
    (ReadingText, READING),
    (WritingPrompt, WRITING),
    (Skill, SKILL),
    (Mission, MISSION),
]


# --- no flag in any file ------------------------------------------------------


@pytest.mark.parametrize(("model", "fields"), MODELS, ids=lambda v: getattr(v, "__name__", ""))
def test_every_content_model_still_accepts_its_content(model, fields) -> None:
    model.model_validate(fields)


@pytest.mark.parametrize("key", REVIEW_KEYS)
@pytest.mark.parametrize(("model", "fields"), MODELS, ids=lambda v: getattr(v, "__name__", ""))
def test_a_review_key_is_refused_and_the_message_says_where_it_lives(model, fields, key) -> None:
    """Refused rather than ignored: several of these models ignore unknown keys,
    and a silently ignored `reviewed: true` is the mistake that looks like it
    worked."""
    value = True if key == "reviewed" else "someone"
    with pytest.raises(ValidationError) as raised:
        model.model_validate({**fields, key: value})
    assert "database" in str(raised.value)
    assert "gjennomgang" in str(raised.value)


def test_no_committed_content_file_carries_a_review_key() -> None:
    offenders = []
    for path in sorted((REPO_ROOT / "data").rglob("*.yaml")):
        found: list[str] = []

        def walk(node: object, found: list[str] = found) -> None:
            if isinstance(node, dict):
                found.extend(key for key in REVIEW_KEYS if key in node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(yaml.safe_load(path.read_text(encoding="utf-8")))
        if found:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {sorted(set(found))}")
    assert offenders == []


def test_the_old_environment_switch_is_gone() -> None:
    assert not hasattr(Settings(), "include_unreviewed_items")
    source = (REPO_ROOT / "src" / "pensum" / "config.py").read_text(encoding="utf-8")
    assert "PENSUM_INCLUDE_UNREVIEWED" not in source


# --- fingerprints ---------------------------------------------------------------


def test_a_fingerprint_is_stable_for_the_same_content() -> None:
    assert fingerprint(QuizItem.model_validate(ITEM)) == fingerprint(QuizItem.model_validate(ITEM))


@pytest.mark.parametrize(
    "change",
    [
        {"prompt": {"nb": "Hva er 2 + 2?", "en": "What is two plus two?"}},
        {"prompt": {"nb": "Hva blir 2 + 2?", "en": "What is 2 + 2?"}},
        {"answer": 5},
        {"difficulty": 2},
    ],
)
def test_a_changed_word_in_either_language_changes_the_fingerprint(change) -> None:
    before = fingerprint(QuizItem.model_validate(ITEM))
    after = fingerprint(QuizItem.model_validate({**ITEM, **change}))
    assert before != after


def test_a_field_left_at_its_default_does_not_count() -> None:
    """So adding an optional field to a schema does not return every piece of
    content on every instance to pending."""
    explicit = QuizItem.model_validate({**ITEM, "tolerance": 0.0})
    assert fingerprint(explicit) == fingerprint(QuizItem.model_validate(ITEM))


# --- the ledger -----------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return ReviewStore(tmp_path / "reviews.db")


def test_with_no_decision_everything_is_pending(store: ReviewStore) -> None:
    ledger = ReviewLedger(store)
    assert ledger.state("item", "KM1-01", "abc") == "pending"
    assert not ledger.publishes("item", "KM1-01", "abc")


def test_an_approval_of_this_content_publishes_it(store: ReviewStore) -> None:
    store.record(decision("item", "KM1-01", "abc"))
    ledger = ReviewLedger(store)
    assert ledger.state("item", "KM1-01", "abc") == "approved"
    assert ledger.publishes("item", "KM1-01", "abc")


def test_an_approval_of_other_content_is_changed_and_withheld(store: ReviewStore) -> None:
    store.record(decision("item", "KM1-01", "abc"))
    ledger = ReviewLedger(store)
    assert ledger.state("item", "KM1-01", "def") == "changed"
    assert not ledger.publishes("item", "KM1-01", "def")


def test_a_rejection_withholds(store: ReviewStore) -> None:
    store.record(decision("reading", "tekst-1", "abc", verdict="rejected"))
    ledger = ReviewLedger(store)
    assert ledger.state("reading", "tekst-1", "abc") == "rejected"
    assert not ledger.publishes("reading", "tekst-1", "abc")


def test_deciding_twice_replaces_rather_than_accumulates(store: ReviewStore) -> None:
    store.record(decision("item", "KM1-01", "abc"))
    store.record(decision("item", "KM1-01", "abc", verdict="rejected"))
    assert len(store.decisions()) == 1
    assert ReviewLedger(store).state("item", "KM1-01", "abc") == "rejected"


def test_clearing_makes_it_pending_again(store: ReviewStore) -> None:
    store.record(decision("item", "KM1-01", "abc"))
    store.clear("item", "KM1-01")
    assert ReviewLedger(store).state("item", "KM1-01", "abc") == "pending"


def test_recording_many_is_one_write(store: ReviewStore) -> None:
    written = store.record_many([decision("item", f"KM1-0{n}", "abc") for n in range(1, 6)])
    assert written == 5
    assert len(store.decisions()) == 5


def test_nothing_touches_the_disk_until_asked(tmp_path: Path) -> None:
    """The app module builds an app at import; importing must not create a file."""
    path = tmp_path / "deep" / "er" / "pensum.db"
    store = ReviewStore(path)
    ReviewLedger(store)
    assert not path.exists()
    store.decisions()
    assert path.exists()


# --- a library with and without decisions ----------------------------------------


def bank() -> ItemBank:
    return ItemBank(
        [
            ItemSet(
                subject="MAT01-06",
                goal_set="KV1",
                items=(QuizItem.model_validate(ITEM),),
                templates=(ItemTemplate.model_validate(TEMPLATE),),
            )
        ]
    )


def test_a_library_with_no_ledger_serves_nothing() -> None:
    assert bank().for_goal_set("KV1") == []
    assert not bank().has_quiz("KV1")


def test_a_library_with_an_empty_ledger_serves_nothing(tmp_path: Path) -> None:
    served = bank().with_ledger(ledger_at(tmp_path / "db.sqlite"))
    assert served.for_goal_set("KV1") == []
    assert served.has_authored("KV1")


def test_approving_serves_it_and_asking_for_everything_still_works(tmp_path: Path) -> None:
    items = bank()
    assert len(items.for_goal_set("KV1", unreviewed=True)) == 2
    approve_all(ledger_at(tmp_path / "db.sqlite"), items=items)
    assert len(items.for_goal_set("KV1")) == 2


def test_a_template_is_decided_once_for_every_instance(tmp_path: Path) -> None:
    items = bank()
    ledger = ledger_at(tmp_path / "db.sqlite")
    items.with_ledger(ledger)
    ledger.store.record(decision("item", "KM1-T1", items.fingerprint("KM1-T1")))
    ledger.reload()

    served = items.for_goal_set("KV1")
    assert [i.id.split("#")[0] for i in served] == ["KM1-T1"]
    for instance in ItemTemplate.model_validate(TEMPLATE).instances():
        assert items.review_state(instance.id) == "approved"
    assert items.review_state("KM1-01") == "pending"


def test_editing_approved_content_returns_it_to_pending(tmp_path: Path) -> None:
    """The whole point of the fingerprint: an approval is for what was read."""
    path = tmp_path / "db.sqlite"
    original = ReadingSet(subject="NOR01-08", goal_set="KV1", texts=[ReadingText(**READING)])
    library = ReadingLibrary([original], ReadingLibrary.load().norms)
    approve_all(ledger_at(path), reading=library)
    assert [t.id for t in library.for_goal_set("KV1")] == ["tekst-1"]

    edited = ReadingSet(
        subject="NOR01-08",
        goal_set="KV1",
        texts=[ReadingText(**{**READING, "title": "Katten som ikke sov"})],
    )
    restarted = ReadingLibrary([edited], ReadingLibrary.load().norms).with_ledger(ledger_at(path))
    assert restarted.for_goal_set("KV1") == []
    assert restarted.review_state("tekst-1") == "changed"


# --- migration --------------------------------------------------------------------

OLD_SCHEMA = """
CREATE TABLE content_reviews (
    kind        TEXT NOT NULL,
    content_id  TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    by_sub      TEXT NOT NULL,
    by_name     TEXT NOT NULL,
    note        TEXT,
    decided_at  TEXT NOT NULL,
    PRIMARY KEY (kind, content_id)
);
"""


def test_a_database_from_before_fingerprints_migrates_and_its_rows_count_as_pending(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    with connection:
        connection.executescript(OLD_SCHEMA)
        connection.execute(
            "INSERT INTO content_reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("item", "KM1-01", "approved", "u-1", "Voksen", None, datetime.now(UTC).isoformat()),
        )
    connection.close()

    store = ReviewStore(path)
    decisions = store.decisions()
    assert decisions[("item", "KM1-01")].fingerprint is None

    items = bank().with_ledger(ReviewLedger(store))
    assert items.review_state("KM1-01") == "pending"
    assert items.for_goal_set("KV1") == []

    columns = {
        row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(content_reviews)")
    }
    assert "fingerprint" in columns


def test_migrating_twice_is_harmless(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    ReviewStore(path).record(decision("item", "KM1-01", "abc"))
    assert ReviewLedger(ReviewStore(path)).state("item", "KM1-01", "abc") == "approved"


# --- always a database -------------------------------------------------------------


def test_with_no_path_configured_the_default_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENSUM_DATABASE_PATH", raising=False)
    settings = Settings.from_env()
    assert settings.database_path is None
    assert settings.database_file == pensum.config.DEFAULT_DATABASE_PATH


def test_the_default_lives_in_the_apps_own_data_directory() -> None:
    """Its own directory under data/, so a volume mounted there hides nothing
    else, and `.gitignore` can name it. Read from the source, because the suite
    redirects the value itself so that no test writes into the checkout."""
    assert pensum.config.REPO_ROOT == REPO_ROOT
    source = (REPO_ROOT / "src" / "pensum" / "config.py").read_text(encoding="utf-8")
    assert 'DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "instance" / "pensum.db"' in source
    assert "data/instance/" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")


def test_a_configured_path_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PENSUM_DATABASE_PATH", str(tmp_path / "x.db"))
    assert Settings.from_env().database_file == tmp_path / "x.db"


def test_an_app_with_no_path_keeps_its_decisions_at_the_default(
    default_database_in_tmp: Path,
) -> None:
    from pensum.catalogue.loader import Catalogue
    from pensum.web.app import create_app

    app = create_app(Catalogue.load(), bank(), settings=Settings())
    assert app.state.review_store.path == default_database_in_tmp
    assert not default_database_in_tmp.parent.exists()
    app.state.review_store.record(decision("item", "KM1-01", "abc"))
    assert default_database_in_tmp.exists()


def test_sign_in_alone_turns_on_score_history() -> None:
    settings = Settings(
        oidc_issuer="https://id.example.com", oidc_client_id="p", oidc_client_secret="s"
    )
    assert settings.history_enabled
    assert not Settings().history_enabled
