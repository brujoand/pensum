"""The review page, and what a decision on it actually changes.

Two halves. The store and ledger are tested directly, because the rule they
implement -- a recorded decision beats the file, in both directions -- is the
whole feature in one method. The page is tested end to end, because the promise
worth protecting is not that a button renders: it is that approving something
puts it in front of a pupil, and that rejecting something takes it away again.

The content is a fixture rather than a passage from `data/reading/`, for the
reason `test_review_gate` gives: reviewing committed content is the normal end
of its life, and a test anchored to it fails on the day someone does the work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pensum.auth.cookies import LOGIN_COOKIE, CookieCodec
from pensum.auth.models import User
from pensum.catalogue.loader import Catalogue
from pensum.config import Settings
from pensum.items.loader import ItemBank
from pensum.reading.library import ReadingLibrary
from pensum.reading.schema import ReadingSet, ReadingText
from pensum.review.queue import counts, entries, find
from pensum.review.store import Decision, ReviewLedger, ReviewStore
from pensum.web.app import create_app
from pensum.writing.library import WritingLibrary, load_alphabet
from pensum.writing.schema import WritingPrompt, WritingSet

ORIGIN = "https://pensum.example.com"
SECRET = "test-secret"

ADMIN = User(sub="u-admin", name="Voksen", groups=("pensum-admins",))
PUPIL = User(sub="u-1", name="Ola", groups=("pupils",))

SUBJECT = "NOR01-08"
GOAL_SET = "KV1107"
GOAL = "KM14140"
READING_PATH = f"/nb/klasse/2/{SUBJECT}/lesing"
REVIEW_PATH = "/nb/admin/gjennomgang"

DRAFT_ID = "utkast-paraplyen"
DRAFT_TITLE = "Paraplyen som ikke ville ut"
WRITING_DRAFT_ID = "utkast-skriving"


def draft() -> ReadingSet:
    return ReadingSet(
        subject=SUBJECT,
        goal_set=GOAL_SET,
        texts=[
            ReadingText(
                id=DRAFT_ID,
                goal=GOAL,
                language="nb",
                title=DRAFT_TITLE,
                body=(
                    "Paraplyen min liker ikke regn.\n"
                    "Den blir sur hver gang jeg tar den med ut.\n"
                    "I dag ble den hjemme, og da var det sol hele dagen.\n"
                ),
                difficulty=1,
                source="pensum",
                reviewed=False,
            )
        ],
    )


def writing_draft() -> WritingSet:
    return WritingSet(
        subject=SUBJECT,
        goal_set=GOAL_SET,
        prompts=[
            WritingPrompt(
                id=WRITING_DRAFT_ID,
                goal="KM14147",
                language="nb",
                title="Bokstaver ingen har lest ennå",
                kind="letters",
                text="il",
                difficulty=1,
                source="pensum",
                reviewed=False,
            )
        ],
    )


def settings_with(tmp_path: Path, **overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "oidc_issuer": "https://id.example.com",
        "oidc_client_id": "pensum",
        "oidc_client_secret": "s3cret",
        "admin_group": "pensum-admins",
        "base_url": ORIGIN,
        "session_secret": SECRET,
        "database_path": tmp_path / "pensum.db",
    }
    return Settings(**(defaults | overrides))


def build(settings: Settings) -> tuple[FastAPI, TestClient]:
    app = create_app(
        Catalogue.load(),
        ItemBank.load(),
        settings=settings,
        reading=ReadingLibrary([draft()], ReadingLibrary.load().norms),
        writing=WritingLibrary([writing_draft()], load_alphabet()),
    )
    return app, TestClient(app, base_url=ORIGIN)


def sign_in(client: TestClient, user: User) -> None:
    client.cookies.set(
        LOGIN_COOKIE, CookieCodec(SECRET).dump_login(user), domain="pensum.example.com"
    )


def approve(client: TestClient, kind: str, content_id: str, verdict: str = "approved"):
    return client.post(
        f"{REVIEW_PATH}/{kind}/{content_id}",
        data={"verdict": verdict, "show": "pending", "filter_kind": "all"},
        follow_redirects=False,
    )


# --- the rule, on its own --------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> ReviewStore:
    return ReviewStore(tmp_path / "reviews.db")


def decision(content_id: str, verdict: str) -> Decision:
    return Decision(
        kind="reading",
        content_id=content_id,
        verdict=verdict,
        by_sub=ADMIN.sub,
        by_name=ADMIN.name,
        decided_at=datetime.now(UTC),
    )


def test_with_no_decision_the_file_still_decides(store: ReviewStore) -> None:
    ledger = ReviewLedger(store)

    assert ledger.publishes("reading", "nothing-decided", True)
    assert not ledger.publishes("reading", "nothing-decided", False)


def test_an_approval_publishes_something_the_file_calls_a_draft(store: ReviewStore) -> None:
    store.record(decision(DRAFT_ID, "approved"))
    ledger = ReviewLedger(store)

    assert ledger.publishes("reading", DRAFT_ID, False)


def test_a_rejection_withdraws_something_the_file_calls_reviewed(store: ReviewStore) -> None:
    """The half that makes this usable in an emergency: whoever noticed can take
    it down, rather than whoever can cut a build."""
    store.record(decision(DRAFT_ID, "rejected"))
    ledger = ReviewLedger(store)

    assert not ledger.publishes("reading", DRAFT_ID, True)


def test_deciding_twice_replaces_rather_than_accumulates(store: ReviewStore) -> None:
    store.record(decision(DRAFT_ID, "approved"))
    store.record(decision(DRAFT_ID, "rejected"))

    assert len(store.decisions()) == 1
    assert not ReviewLedger(store).publishes("reading", DRAFT_ID, False)


def test_clearing_hands_the_question_back_to_the_file(store: ReviewStore) -> None:
    store.record(decision(DRAFT_ID, "approved"))
    store.clear("reading", DRAFT_ID)
    ledger = ReviewLedger(store)

    assert not ledger.publishes("reading", DRAFT_ID, False)
    assert ledger.publishes("reading", DRAFT_ID, True)


# --- the queue -------------------------------------------------------------


def test_the_queue_lists_all_three_kinds(tmp_path: Path) -> None:
    app, _ = build(settings_with(tmp_path))
    collected = entries(app.state.items, app.state.reading, app.state.writing, app.state.reviews)

    kinds = {entry.kind for entry in collected}
    assert kinds == {"item", "reading", "writing"}
    assert find(collected, "reading", DRAFT_ID) is not None


def test_a_decision_moves_a_row_out_of_pending(tmp_path: Path) -> None:
    app, _ = build(settings_with(tmp_path))
    before = counts(
        entries(app.state.items, app.state.reading, app.state.writing, app.state.reviews)
    )

    app.state.review_store.record(decision(DRAFT_ID, "approved"))
    app.state.reviews.reload()
    after = counts(
        entries(app.state.items, app.state.reading, app.state.writing, app.state.reviews)
    )

    assert after.pending == before.pending - 1
    assert after.published == before.published + 1
    assert after.total == before.total


def test_an_approval_that_disagrees_with_the_file_is_marked_as_such(tmp_path: Path) -> None:
    app, _ = build(settings_with(tmp_path))
    app.state.review_store.record(decision(DRAFT_ID, "approved"))
    app.state.reviews.reload()

    collected = entries(app.state.items, app.state.reading, app.state.writing, app.state.reviews)
    entry = find(collected, "reading", DRAFT_ID)
    assert entry is not None
    assert entry.overridden


# --- the page --------------------------------------------------------------


def test_an_anonymous_visitor_cannot_open_the_review_page(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))

    assert client.get(REVIEW_PATH).status_code == 401


def test_a_signed_in_pupil_cannot_open_the_review_page(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)

    assert client.get(REVIEW_PATH).status_code == 403


def test_a_pupil_cannot_publish_anything_by_posting(tmp_path: Path) -> None:
    """The negative case that matters most: the form is the publish button, and
    it must be as closed as the page it lives on."""
    app, client = build(settings_with(tmp_path))
    sign_in(client, PUPIL)

    assert approve(client, "reading", DRAFT_ID).status_code == 403
    assert app.state.review_store.decisions() == {}


def test_an_administrator_sees_the_draft_in_the_queue(tmp_path: Path) -> None:
    _, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN)

    body = client.get(REVIEW_PATH).text
    assert DRAFT_TITLE in body
    assert "Paraplyen min liker ikke regn." in body


def test_the_page_is_absent_when_there_is_no_database(tmp_path: Path) -> None:
    """No database means nothing to record a decision in, and a review page that
    cannot record one would be a button that lies."""
    _, client = build(settings_with(tmp_path, database_path=None))
    sign_in(client, ADMIN)

    assert client.get(REVIEW_PATH).status_code == 404


# --- what a decision does to what a pupil sees -----------------------------


def test_approving_puts_the_passage_in_front_of_a_pupil(tmp_path: Path) -> None:
    """The whole point of the feature, asserted end to end."""
    settings = settings_with(tmp_path)
    app, admin_client = build(settings)
    sign_in(admin_client, ADMIN)

    pupil_client = TestClient(app, base_url=ORIGIN)
    assert pupil_client.get(READING_PATH).status_code == 404

    assert approve(admin_client, "reading", DRAFT_ID).status_code == 303
    assert DRAFT_TITLE in pupil_client.get(READING_PATH).text


def test_rejecting_takes_it_away_again(tmp_path: Path) -> None:
    app, admin_client = build(settings_with(tmp_path))
    sign_in(admin_client, ADMIN)
    pupil_client = TestClient(app, base_url=ORIGIN)

    approve(admin_client, "reading", DRAFT_ID)
    assert pupil_client.get(READING_PATH).status_code == 200

    approve(admin_client, "reading", DRAFT_ID, verdict="rejected")
    assert pupil_client.get(READING_PATH).status_code == 404


def test_the_decision_takes_effect_without_waiting_for_the_refresh(tmp_path: Path) -> None:
    """The ledger caches, so the write path has to invalidate it. Without the
    reload this passes half a minute later, which is the kind of bug that is
    reported as "it did not work" and cannot be reproduced."""
    app, admin_client = build(settings_with(tmp_path))
    sign_in(admin_client, ADMIN)

    # A long TTL, so anything but an explicit reload leaves the page stale.
    app.state.reviews._refresh_seconds = 3600.0
    approve(admin_client, "reading", DRAFT_ID)

    assert TestClient(app, base_url=ORIGIN).get(READING_PATH).status_code == 200


def test_a_decision_about_content_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN)

    assert approve(client, "reading", "ingen-slik-tekst").status_code == 404
    assert approve(client, "vaffel", DRAFT_ID).status_code == 404
    assert app.state.review_store.decisions() == {}


def test_an_unknown_verdict_is_refused(tmp_path: Path) -> None:
    app, client = build(settings_with(tmp_path))
    sign_in(client, ADMIN)

    assert approve(client, "reading", DRAFT_ID, verdict="kanskje").status_code == 422
    assert app.state.review_store.decisions() == {}
