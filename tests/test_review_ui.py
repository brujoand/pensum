"""The review page, and what a decision on it actually changes.

The page is how content becomes live, so it is tested end to end: the promise
worth protecting is not that a button renders, it is that approving something
puts it in front of a pupil, that rejecting something takes it away again, that
editing it afterwards takes it away until someone looks again, and that a bulk
approval does exactly what the confirmation said it would.

The store and ledger rules on their own are in `test_review_state`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pensum.auth.cookies import LOGIN_COOKIE, CookieCodec
from pensum.auth.models import User
from pensum.catalogue.loader import Catalogue
from pensum.config import Settings
from pensum.items.loader import ItemBank
from pensum.items.primitives import primitive_for
from pensum.items.schema import QuizItem
from pensum.items.sets import ItemSet
from pensum.items.template import ItemTemplate
from pensum.reading.library import ReadingLibrary
from pensum.reading.schema import ReadingSet, ReadingText
from pensum.review.queue import Libraries, counts, entries, find
from pensum.web.app import create_app
from pensum.web.deps import get_missions
from pensum.web.review_routes import PAGE_SIZE
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
WRITING_PATH = f"/nb/klasse/2/{SUBJECT}/skriving"
REVIEW_PATH = "/nb/admin/gjennomgang"
BULK_PATH = f"{REVIEW_PATH}/samlet"
TRY_PATH = f"{REVIEW_PATH}/proev"

DRAFT_ID = "utkast-paraplyen"
DRAFT_TITLE = "Paraplyen som ikke ville ut"
WRITING_DRAFT_ID = "utkast-skriving"

CATALOGUE = Catalogue.load()
NORMS = ReadingLibrary.load().norms


def passage(title: str = DRAFT_TITLE) -> ReadingText:
    return ReadingText(
        id=DRAFT_ID,
        goal=GOAL,
        language="nb",
        title=title,
        body=(
            "Paraplyen min liker ikke regn.\n"
            "Den blir sur hver gang jeg tar den med ut.\n"
            "I dag ble den hjemme, og da var det sol hele dagen.\n"
        ),
        difficulty=1,
        source="pensum",
    )


def reading(title: str = DRAFT_TITLE) -> ReadingLibrary:
    return ReadingLibrary(
        [ReadingSet(subject=SUBJECT, goal_set=GOAL_SET, texts=[passage(title)])], NORMS
    )


def writing() -> WritingLibrary:
    return WritingLibrary(
        [
            WritingSet(
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
                    )
                ],
            )
        ],
        load_alphabet(),
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


def build(
    tmp_path: Path,
    *,
    items: ItemBank | None = None,
    reading_library: ReadingLibrary | None = None,
) -> tuple[FastAPI, TestClient]:
    app = create_app(
        CATALOGUE,
        items if items is not None else ItemBank([]),
        settings=settings_with(tmp_path),
        reading=reading_library if reading_library is not None else reading(),
        writing=writing(),
    )
    return app, TestClient(app, base_url=ORIGIN)


def sign_in(client: TestClient, user: User) -> None:
    client.cookies.set(
        LOGIN_COOKIE, CookieCodec(SECRET).dump_login(user), domain="pensum.example.com"
    )


def admin(tmp_path: Path, **kwargs) -> tuple[FastAPI, TestClient]:
    app, client = build(tmp_path, **kwargs)
    sign_in(client, ADMIN)
    return app, client


def fingerprint_of(app: FastAPI, kind: str, content_id: str) -> str:
    entry = find(all_entries(app), kind, content_id)
    assert entry is not None
    return entry.fingerprint


def all_entries(app: FastAPI):
    state = app.state
    libraries = Libraries(
        items=state.items,
        reading=state.reading,
        writing=state.writing,
        skills=state.skills,
        missions=get_missions_of(app),
    )
    return entries(libraries, state.reviews, CATALOGUE)


def get_missions_of(app: FastAPI):
    class _Request:
        def __init__(self, app: FastAPI) -> None:
            self.app = app

    return get_missions(_Request(app))  # type: ignore[arg-type]


def decide(
    client: TestClient,
    app: FastAPI,
    kind: str,
    content_id: str,
    verdict: str = "approved",
    *,
    fingerprint: str | None = None,
    note: str = "",
):
    return client.post(
        f"{REVIEW_PATH}/{kind}/{content_id}",
        data={
            "verdict": verdict,
            "fingerprint": fingerprint
            if fingerprint is not None
            else fingerprint_of(app, kind, content_id),
            "note": note,
        },
        follow_redirects=False,
    )


# --- the queue -------------------------------------------------------------


def test_the_queue_holds_every_reviewable_kind(tmp_path: Path) -> None:
    app, _ = build(tmp_path, items=ItemBank.load())
    kinds = {entry.kind for entry in all_entries(app)}
    assert kinds == {"item", "reading", "writing", "skill", "mission"}


def test_everything_starts_pending(tmp_path: Path) -> None:
    app, _ = build(tmp_path, items=ItemBank.load())
    tally = counts(all_entries(app))
    assert tally.pending == tally.total > 300


def test_a_decision_moves_a_row_out_of_pending(tmp_path: Path) -> None:
    app, client = admin(tmp_path)
    before = counts(all_entries(app))

    assert decide(client, app, "reading", DRAFT_ID).status_code == 303
    after = counts(all_entries(app))

    assert after.pending == before.pending - 1
    assert after.approved == before.approved + 1
    assert after.total == before.total


# --- who may use it ----------------------------------------------------------


def test_an_anonymous_visitor_cannot_open_the_review_page(tmp_path: Path) -> None:
    _, client = build(tmp_path)
    assert client.get(REVIEW_PATH).status_code == 401


def test_a_signed_in_pupil_cannot_open_the_review_page(tmp_path: Path) -> None:
    _, client = build(tmp_path)
    sign_in(client, PUPIL)
    assert client.get(REVIEW_PATH).status_code == 403


def test_a_pupil_cannot_publish_anything_by_posting(tmp_path: Path) -> None:
    """The negative case that matters most: the form is the publish button, and
    it must be as closed as the page it lives on -- one piece or all of them."""
    app, client = build(tmp_path)
    sign_in(client, PUPIL)

    assert decide(client, app, "reading", DRAFT_ID).status_code == 403
    bulk = client.post(BULK_PATH, data={"verdict": "approved", "state": "all", "confirm": "yes"})
    assert bulk.status_code == 403
    assert client.post(TRY_PATH, data={"item_id": "x"}).status_code == 403
    assert app.state.review_store.decisions() == {}


def test_an_administrator_sees_the_draft_in_the_queue(tmp_path: Path) -> None:
    _, client = admin(tmp_path)
    body = client.get(REVIEW_PATH).text
    assert DRAFT_TITLE in body
    assert "Paraplyen min liker ikke regn." in body


# --- what a decision does to what a pupil sees -----------------------------


def test_approving_puts_the_passage_in_front_of_a_pupil(tmp_path: Path) -> None:
    """The whole point of the feature, asserted end to end."""
    app, admin_client = admin(tmp_path)
    pupil_client = TestClient(app, base_url=ORIGIN)
    assert pupil_client.get(READING_PATH).status_code == 404

    assert decide(admin_client, app, "reading", DRAFT_ID).status_code == 303
    assert DRAFT_TITLE in pupil_client.get(READING_PATH).text


def test_rejecting_takes_it_away_again(tmp_path: Path) -> None:
    app, admin_client = admin(tmp_path)
    pupil_client = TestClient(app, base_url=ORIGIN)

    decide(admin_client, app, "reading", DRAFT_ID)
    assert pupil_client.get(READING_PATH).status_code == 200

    decide(admin_client, app, "reading", DRAFT_ID, verdict="rejected")
    assert pupil_client.get(READING_PATH).status_code == 404


def test_clearing_returns_it_to_pending(tmp_path: Path) -> None:
    app, admin_client = admin(tmp_path)
    decide(admin_client, app, "reading", DRAFT_ID)
    decide(admin_client, app, "reading", DRAFT_ID, verdict="clear")
    assert TestClient(app, base_url=ORIGIN).get(READING_PATH).status_code == 404
    assert app.state.review_store.decisions() == {}


def test_editing_after_approval_withholds_it_and_the_page_says_why(tmp_path: Path) -> None:
    """The same database, an edited file: the approval was for other words."""
    app, admin_client = admin(tmp_path)
    decide(admin_client, app, "reading", DRAFT_ID)

    edited_app, edited_admin = admin(tmp_path, reading_library=reading("Paraplyen som ville ut"))
    pupil_client = TestClient(edited_app, base_url=ORIGIN)
    assert pupil_client.get(READING_PATH).status_code == 404

    page = edited_admin.get(REVIEW_PATH, params={"state": "changed"}).text
    assert "Paraplyen som ville ut" in page
    assert "Endret siden avgjørelsen" in page


def test_a_decision_on_what_the_reviewer_did_not_see_is_refused(tmp_path: Path) -> None:
    """The form carries the fingerprint of what was on screen. A page rendered
    before the file changed cannot approve the new words."""
    app, client = admin(tmp_path)

    response = decide(client, app, "reading", DRAFT_ID, fingerprint="0" * 64)

    assert response.status_code == 303
    assert "stale=" in response.headers["location"]
    assert app.state.review_store.decisions() == {}
    assert "endret siden du åpnet siden" in client.get(response.headers["location"]).text


def test_the_decision_takes_effect_without_waiting_for_the_refresh(tmp_path: Path) -> None:
    """The ledger caches, so the write path has to invalidate it."""
    app, admin_client = admin(tmp_path)
    app.state.reviews._refresh_seconds = 3600.0
    app.state.reviews.reload()

    decide(admin_client, app, "reading", DRAFT_ID)

    assert TestClient(app, base_url=ORIGIN).get(READING_PATH).status_code == 200


def test_who_decided_when_and_why_is_shown(tmp_path: Path) -> None:
    app, client = admin(tmp_path)
    decide(client, app, "reading", DRAFT_ID, verdict="rejected", note="For trist for 2. trinn")

    page = client.get(REVIEW_PATH, params={"state": "rejected"}).text
    assert "Avgjort av Voksen" in page
    assert "For trist for 2. trinn" in page
    stored = app.state.review_store.decisions()[("reading", DRAFT_ID)]
    assert stored.note == "For trist for 2. trinn"
    assert stored.by_sub == ADMIN.sub


def test_a_decision_about_content_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    app, client = admin(tmp_path)
    missing = client.post(f"{REVIEW_PATH}/reading/ingen-slik-tekst", data={"verdict": "approved"})
    unknown_kind = client.post(f"{REVIEW_PATH}/vaffel/{DRAFT_ID}", data={"verdict": "approved"})

    assert missing.status_code == 404
    assert unknown_kind.status_code == 404
    assert app.state.review_store.decisions() == {}


def test_an_unknown_verdict_is_refused(tmp_path: Path) -> None:
    app, client = admin(tmp_path)
    assert decide(client, app, "reading", DRAFT_ID, verdict="kanskje").status_code == 422
    assert app.state.review_store.decisions() == {}


# --- every kind, decided on this page ----------------------------------------


def test_skills_and_missions_are_decided_here_too(tmp_path: Path) -> None:
    app, client = admin(tmp_path)
    skill = app.state.skills.for_subject("MAT01-06").skills[0]
    mission = get_missions_of(app).for_subject("MAT01-06").missions[0]

    assert decide(client, app, "skill", skill.id).status_code == 303
    assert decide(client, app, "mission", mission.id).status_code == 303

    assert app.state.skills.review_state(skill.id) == "approved"
    assert get_missions_of(app).review_state(mission.id) == "approved"


def test_a_mission_page_opens_for_a_pupil_only_once_approved(tmp_path: Path) -> None:
    app, client = admin(tmp_path)
    mission = get_missions_of(app).for_subject("MAT01-06").missions[0]
    pupil_client = TestClient(app, base_url=ORIGIN)
    path = f"/nb/oppdrag/{mission.id}"

    assert pupil_client.get(path).status_code == 404
    assert client.get(path).status_code == 200  # an administrator reads it first

    decide(client, app, "mission", mission.id)
    assert pupil_client.get(path).status_code == 200


# --- a template is one piece ----------------------------------------------------


def template_bank() -> ItemBank:
    template = ItemTemplate.model_validate(
        {
            "id": "KM13228-T1",
            "goal": "KM13228",
            "difficulty": 2,
            "params": {"a": {"min": 3, "max": 9}},
            "answer": "a + 2",
            "prompt": {"nb": "Hva er {a} + 2?", "en": "What is {a} + 2?"},
            "explanation": {"nb": "To mer enn {a}.", "en": "Two more than {a}."},
        }
    )
    return ItemBank([ItemSet(subject="MAT01-06", goal_set="KV1021", templates=(template,))])


def test_a_template_is_shown_live_with_other_variants_and_approved_as_one(tmp_path: Path) -> None:
    app, client = admin(tmp_path, items=template_bank())

    page = client.get(REVIEW_PATH, params={"kind": "item"}).text
    assert "Spørsmålsmal" in page
    assert "7 varianter" in page
    assert "Hva er 3 + 2?" in page  # the first variant, as a pupil meets it
    assert "Hva er 4 + 2?" in page  # and another, with its answer
    assert 'name="item_id" value="KM13228-T1#3"' in page

    assert app.state.items.for_goal_set("KV1021") == []
    assert decide(client, app, "item", "KM13228-T1").status_code == 303
    served = app.state.items.for_goal_set("KV1021")
    assert len(served) == 1
    assert served[0].id.startswith("KM13228-T1#")


# --- the page renders every kind, in both locales ----------------------------------


@pytest.fixture(scope="module")
def everything(tmp_path_factory: pytest.TempPathFactory) -> tuple[FastAPI, TestClient]:
    app = create_app(
        CATALOGUE,
        ItemBank.load(),
        settings=settings_with(tmp_path_factory.mktemp("everything")),
        reading=ReadingLibrary.load(),
        writing=WritingLibrary.load(),
    )
    client = TestClient(app, base_url=ORIGIN)
    sign_in(client, ADMIN)
    return app, client


def primitive_examples() -> dict[str, tuple[str, str, int]]:
    """One committed item per hands-on primitive: its id, goal set and page."""
    found: dict[str, tuple[str, str, int]] = {}
    for item_set in ItemBank.load().item_sets:
        for index, item in enumerate(item_set.items):
            if primitive_for(item) is not None and item.type not in found:
                found[item.type] = (item.id, item_set.goal_set, index // PAGE_SIZE + 1)
    return found


EXAMPLES = primitive_examples()


@pytest.mark.parametrize("locale", ["nb", "en"])
@pytest.mark.parametrize("primitive", sorted(EXAMPLES))
def test_every_primitive_is_rendered_live_with_its_script(
    everything: tuple[FastAPI, TestClient], primitive: str, locale: str
) -> None:
    _, client = everything
    item_id, goal_set, page = EXAMPLES[primitive]
    response = client.get(
        f"/{locale}/admin/gjennomgang",
        params={"kind": "item", "goal_set": goal_set, "state": "all", "page": page},
    )
    assert response.status_code == 200
    body = response.text
    assert f'value="{item_id}"' in body
    # The live board, the script that drives it, and the answer beneath it. The
    # number line answers on its own figure rather than on an activity board.
    board = "data-number-line" if primitive == "number_line" else f'data-activity="{primitive}"'
    assert board in body
    assert "/static/primitives/core.js" in body
    assert ("Løsning" if locale == "nb" else "Solution") in body


@pytest.mark.parametrize("locale", ["nb", "en"])
@pytest.mark.parametrize("kind", ["item", "reading", "writing", "skill", "mission"])
def test_every_kind_renders_in_both_locales(
    everything: tuple[FastAPI, TestClient], kind: str, locale: str
) -> None:
    _, client = everything
    response = client.get(f"/{locale}/admin/gjennomgang", params={"kind": kind, "state": "all"})
    assert response.status_code == 200
    assert 'class="review-entry"' in response.text
    # Every row carries its own decision form, with the fingerprint of what is shown.
    assert response.text.count('name="fingerprint"') == response.text.count('class="review-entry"')


def test_the_page_is_paged_and_says_where_it_is(everything: tuple[FastAPI, TestClient]) -> None:
    _, client = everything
    page = client.get(REVIEW_PATH, params={"state": "all"}).text
    assert re.search(r"Side 1 av \d+", page)
    assert "page=2" in page


def test_filters_narrow_by_subject_and_goal_set(everything: tuple[FastAPI, TestClient]) -> None:
    _, client = everything
    page = client.get(
        REVIEW_PATH, params={"subject": "MAT01-06", "goal_set": "KV1021", "state": "all"}
    ).text
    assert "KV1021" in page
    assert "NOR01-08" not in re.sub(r"<select.*?</select>", "", page, flags=re.S)


# --- trying a question -----------------------------------------------------------


def numeric_bank() -> ItemBank:
    item = QuizItem.model_validate(
        {
            "id": "KM13228-99",
            "goal": "KM13228",
            "type": "numeric",
            "difficulty": 1,
            "prompt": {"nb": "Hva er 2 + 2?", "en": "What is 2 + 2?"},
            "explanation": {"nb": "2 + 2 = 4.", "en": "2 + 2 = 4."},
            "answer": 4,
        }
    )
    return ItemBank([ItemSet(subject="MAT01-06", goal_set="KV1021", items=(item,))])


def test_an_administrator_can_try_a_question_and_nothing_is_recorded(tmp_path: Path) -> None:
    app, client = admin(tmp_path, items=numeric_bank())

    right = client.post(TRY_PATH, data={"item_id": "KM13228-99", "response": "4"})
    wrong = client.post(
        TRY_PATH,
        data={"item_id": "KM13228-99", "response": "5"},
        headers={"HX-Request": "true"},
    )

    assert right.status_code == 200
    assert "Riktig." in right.text
    assert "Tilbake til gjennomgangen" in right.text  # a whole page, without script
    assert "Ikke riktig" in wrong.text
    assert "<html" not in wrong.text  # a fragment, for htmx
    assert app.state.review_store.decisions() == {}


def test_trying_a_question_that_does_not_exist_is_404(tmp_path: Path) -> None:
    _, client = admin(tmp_path, items=numeric_bank())
    assert client.post(TRY_PATH, data={"item_id": "nope"}).status_code == 404


# --- bulk --------------------------------------------------------------------------


def bulk(client: TestClient, verdict: str = "approved", **fields: str):
    return client.post(BULK_PATH, data={"verdict": verdict, **fields}, follow_redirects=False)


def expected_digest(page: str) -> str:
    match = re.search(r'name="expected" value="([0-9a-f]+)"', page)
    assert match, "the confirmation carries the digest of what it counted"
    return match.group(1)


def test_bulk_asks_first_and_writes_nothing_until_confirmed(tmp_path: Path) -> None:
    app, client = admin(tmp_path, items=numeric_bank())

    asked = bulk(client, kind="skill", state="pending")

    assert asked.status_code == 200
    count = len(app.state.skills.for_subject("MAT01-06").skills)
    assert "Godkjenne" in asked.text
    assert app.state.review_store.decisions() == {}
    assert count > 0


def test_bulk_approves_exactly_the_filtered_selection(tmp_path: Path) -> None:
    app, client = admin(tmp_path, items=numeric_bank())
    fields = {"subject": "MAT01-06", "kind": "skill", "state": "pending"}
    selection = [
        e
        for e in all_entries(app)
        if e.kind == "skill" and e.subject == "MAT01-06" and e.state == "pending"
    ]

    asked = bulk(client, **fields)
    assert f"Godkjenne {len(selection)} ting?" in asked.text
    done = bulk(client, **fields, confirm="yes", expected=expected_digest(asked.text), note="Lest")

    assert done.status_code == 303
    assert f"done={len(selection)}" in done.headers["location"]
    decided = app.state.review_store.decisions()
    assert {cid for (_, cid) in decided} == {e.content_id for e in selection}
    assert all(d.note == "Lest" for d in decided.values())
    # Nothing outside the filter moved: the question and the other subjects'
    # skills are still pending.
    assert app.state.items.review_state("KM13228-99") == "pending"
    assert app.state.items.for_goal_set("KV1021") == []
    other = app.state.skills.for_subject("NOR01-08").skills[0]
    assert app.state.skills.review_state(other.id) == "pending"


def test_bulk_reject(tmp_path: Path) -> None:
    app, client = admin(tmp_path, items=numeric_bank())
    asked = bulk(client, "rejected", kind="item", state="pending")
    assert "Avvise 1 ting?" in asked.text
    bulk(
        client,
        "rejected",
        kind="item",
        state="pending",
        confirm="yes",
        expected=expected_digest(asked.text),
    )
    assert app.state.items.review_state("KM13228-99") == "rejected"


def test_bulk_writes_nothing_if_the_selection_changed_since_it_was_counted(
    tmp_path: Path,
) -> None:
    """Someone else decided one of them in between: the count shown is no longer
    the count that would be written, so nothing is."""
    app, client = admin(tmp_path, items=numeric_bank())
    fields = {"kind": "reading", "state": "pending"}
    asked = bulk(client, **fields)
    digest = expected_digest(asked.text)

    decide(client, app, "writing", WRITING_DRAFT_ID)  # unrelated: still the same set
    stale = bulk(client, **{**fields, "kind": "all"}, confirm="yes", expected=digest)

    assert stale.status_code == 200
    assert "Utvalget er endret" in stale.text
    assert set(app.state.review_store.decisions()) == {("writing", WRITING_DRAFT_ID)}


def test_bulk_on_an_empty_selection_says_so(tmp_path: Path) -> None:
    _, client = admin(tmp_path, items=numeric_bank())
    asked = bulk(client, kind="item", state="rejected")
    assert "Utvalget er tomt" in asked.text


def test_bulk_approval_reaches_a_pupil(tmp_path: Path) -> None:
    app, client = admin(tmp_path, items=numeric_bank())
    pupil_client = TestClient(app, base_url=ORIGIN)
    assert pupil_client.post("/nb/klasse/2/MAT01-06/quiz").status_code == 404

    asked = bulk(client, kind="item", state="pending")
    bulk(client, kind="item", state="pending", confirm="yes", expected=expected_digest(asked.text))

    assert (
        pupil_client.post("/nb/klasse/2/MAT01-06/quiz", follow_redirects=False).status_code == 303
    )
