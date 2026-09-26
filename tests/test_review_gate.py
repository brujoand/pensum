"""Who is allowed to see content that is not approved on this instance.

Pensum serves pupils approved content only, and approval is data on the
instance, never a flag in a file (`pensum.review`). An administrator is the
exception: a draft has to be readable in place, labelled, before anyone can
judge whether it is fit.

The assertions that matter here are the negative ones. Every other test in this
suite fails loudly when something stops working; these fail loudly when
something starts working for the wrong person.

The draft is a fixture, deliberately, and not a passage from `data/reading/`,
so the negative assertions do not depend on what happens to be committed. The
committed content gets its own tests at the end: a fresh instance serves none of
it, and approving it serves it.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from review_helpers import approve_app

from pensum.auth.cookies import LOGIN_COOKIE, CookieCodec
from pensum.auth.models import User
from pensum.catalogue.loader import Catalogue
from pensum.config import Settings
from pensum.items.loader import ItemBank
from pensum.reading.library import ReadingLibrary
from pensum.reading.schema import ReadingSet, ReadingText
from pensum.web.app import create_app
from pensum.writing.library import WritingLibrary, load_alphabet
from pensum.writing.schema import WritingPrompt, WritingSet

ORIGIN = "https://pensum.example.com"
SECRET = "test-secret"

ADMIN = User(sub="u-admin", name="Voksen", groups=("pensum-admins",))
PUPIL = User(sub="u-1", name="Ola", groups=("pupils",))

# Norsk after 2. trinn, a real checkpoint, so the subject page renders the way
# it really does. What is fake is only the passage hanging off it.
SUBJECT = "NOR01-08"
GOAL_SET = "KV1107"
GOAL = "KM14140"
READING_PATH = f"/nb/klasse/2/{SUBJECT}/lesing"
WRITING_PATH = f"/nb/klasse/2/{SUBJECT}/skriving"
SUBJECT_PATH = f"/nb/klasse/2/{SUBJECT}"

DRAFT_ID = "utkast-stovsugerkatten"
DRAFT_TITLE = "Katten som trodde den var en støvsuger"
WRITING_DRAFT_ID = "utkast-bokstaver"
WRITING_DRAFT_TITLE = "Bokstaver ingen har sett på ennå"


def draft() -> ReadingSet:
    """One checkpoint whose only passage is not approved.

    Only, because the sharpest form of the negative assertion is that the
    listing 404s outright: a pupil is not shown a thinned-out page, they are
    shown no page.
    """
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
                    "Katten min tror at den er en støvsuger.\n"
                    "Den går rundt i stua og suger opp alt den finner.\n"
                    "I går spiste den en sokk, en blyant og halve avisa.\n"
                ),
                difficulty=1,
                source="pensum",
            )
        ],
    )


def writing_draft() -> WritingSet:
    """The same shape again for handwriting: one checkpoint, one unapproved
    prompt, so the listing 404s outright rather than thinning out."""
    return WritingSet(
        subject=SUBJECT,
        goal_set=GOAL_SET,
        prompts=[
            WritingPrompt(
                id=WRITING_DRAFT_ID,
                goal="KM14147",
                language="nb",
                title=WRITING_DRAFT_TITLE,
                kind="letters",
                text="il",
                difficulty=1,
                source="pensum",
            )
        ],
    )


def settings_with(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "oidc_issuer": "https://id.example.com",
        "oidc_client_id": "pensum",
        "oidc_client_secret": "s3cret",
        "admin_group": "pensum-admins",
        "base_url": ORIGIN,
        "session_secret": SECRET,
    }
    return Settings(**(defaults | overrides))


def build(settings: Settings | None = None) -> tuple[FastAPI, TestClient]:
    # Real norms, because the bands are not what is under test here and a
    # passage with no band renders differently.
    library = ReadingLibrary([draft()], ReadingLibrary.load().norms)
    # Real letterforms, because the alphabet is not what is under test and a
    # prompt whose characters cannot be drawn is withheld for a different reason.
    writing = WritingLibrary([writing_draft()], load_alphabet())
    app = create_app(
        Catalogue.load(),
        ItemBank.load(),
        settings=settings if settings is not None else settings_with(),
        reading=library,
        writing=writing,
    )
    return app, TestClient(app, base_url=ORIGIN)


def sign_in(client: TestClient, user: User) -> None:
    client.cookies.set(
        LOGIN_COOKIE, CookieCodec(SECRET).dump_login(user), domain="pensum.example.com"
    )


# --- the negative cases ----------------------------------------------------


def test_an_anonymous_pupil_sees_no_unapproved_reading() -> None:
    _, client = build()

    assert client.get(READING_PATH).status_code == 404
    assert "/lesing" not in client.get(SUBJECT_PATH).text


def test_a_signed_in_pupil_is_not_an_administrator() -> None:
    """Being signed in is not the qualification. Being in the group is."""
    _, client = build()
    sign_in(client, PUPIL)

    assert client.get(READING_PATH).status_code == 404
    assert "/lesing" not in client.get(SUBJECT_PATH).text


def test_an_unconfigured_instance_has_no_administrators() -> None:
    """With sign-in unconfigured, `current_user` is always None -- so nobody
    qualifies, even carrying a cookie minted with the right secret. This is the
    state the published image runs in."""
    _, client = build(Settings(session_secret=SECRET, base_url=ORIGIN))
    sign_in(client, ADMIN)

    assert client.get(READING_PATH).status_code == 404


def test_a_draft_is_never_reachable_by_guessing_its_url() -> None:
    """The listing is hidden from a pupil; so is the passage behind it."""
    _, client = build()
    sign_in(client, PUPIL)

    assert client.get(f"{READING_PATH}/{DRAFT_ID}").status_code == 404
    assert client.post(f"{READING_PATH}/{DRAFT_ID}/tid", data={"seconds": "30"}).status_code == 404


def test_an_anonymous_pupil_sees_no_unapproved_writing() -> None:
    _, client = build()

    assert client.get(WRITING_PATH).status_code == 404
    assert "/skriving" not in client.get(SUBJECT_PATH).text


def test_a_writing_draft_is_never_reachable_by_guessing_its_url() -> None:
    """Including the endpoint that marks one: a draft that could not be listed
    but could be scored would still be a draft put in front of a child."""
    _, client = build()
    sign_in(client, PUPIL)

    assert client.get(f"{WRITING_PATH}/{WRITING_DRAFT_ID}").status_code == 404
    marked = client.post(
        f"{WRITING_PATH}/{WRITING_DRAFT_ID}/spor", json={"seconds": 5.0, "glyphs": []}
    )
    assert marked.status_code == 404


# --- the positive case -----------------------------------------------------


def test_an_administrator_sees_the_drafts_and_that_they_are_drafts() -> None:
    _, client = build()
    sign_in(client, ADMIN)

    listing = client.get(READING_PATH)

    assert listing.status_code == 200
    assert DRAFT_TITLE in listing.text
    # Marked, not silently mixed in: an unmarked draft would be judged as if it
    # had already passed review.
    assert "Venter på godkjenning" in listing.text


def test_an_administrator_can_read_a_draft_passage_through() -> None:
    _, client = build()
    sign_in(client, ADMIN)

    page = client.get(f"{READING_PATH}/{DRAFT_ID}")
    scored = client.post(f"{READING_PATH}/{DRAFT_ID}/tid", data={"seconds": "45"})

    assert page.status_code == 200
    assert scored.status_code == 200


def test_an_administrator_sees_the_writing_drafts_and_that_they_are_drafts() -> None:
    _, client = build()
    sign_in(client, ADMIN)

    listing = client.get(WRITING_PATH)

    assert listing.status_code == 200
    assert WRITING_DRAFT_TITLE in listing.text
    assert "Venter på godkjenning" in listing.text


def test_the_subject_page_tells_an_administrator_why_it_looks_different() -> None:
    _, client = build()
    sign_in(client, ADMIN)

    page = client.get(SUBJECT_PATH)

    assert "/lesing" in page.text
    assert "logget inn som administrator" in page.text


# --- there is no deployment-wide switch -----------------------------------


def test_the_old_environment_switch_shows_nobody_anything(monkeypatch: pytest.MonkeyPatch) -> None:
    """`PENSUM_INCLUDE_UNREVIEWED` is gone. Setting it must change nothing: an
    instance shows pupils what its administrators approved, and nothing else."""
    monkeypatch.setenv("PENSUM_INCLUDE_UNREVIEWED", "1")
    _, client = build(Settings.from_env())

    assert client.get(READING_PATH).status_code == 404


# --- approved content, and the committed content ---------------------------


@pytest.mark.parametrize("user", [None, PUPIL, ADMIN])
def test_approved_content_is_visible_to_everyone(user: User | None) -> None:
    """The gate only ever withholds what is not approved."""
    app, client = build()
    approve_app(app)
    if user is not None:
        sign_in(client, user)

    assert "Ta quizen" in client.get("/nb/klasse/2/MAT01-06").text
    assert client.get(READING_PATH).status_code == 200
    assert "Venter på godkjenning" not in client.get(READING_PATH).text


def committed_app() -> tuple[FastAPI, TestClient]:
    app = create_app(
        Catalogue.load(), ItemBank.load(), settings=settings_with(), reading=ReadingLibrary.load()
    )
    return app, TestClient(app, base_url=ORIGIN)


def test_a_fresh_instance_serves_a_pupil_none_of_the_committed_content() -> None:
    """Start all pending: every question, passage and prompt in `data/` is
    written, and none of it is approved on a new instance."""
    _, client = committed_app()

    subject = client.get("/nb/klasse/2/MAT01-06")
    assert subject.status_code == 200
    assert "Ta quizen" not in subject.text
    assert "ingen av dem er godkjent" in subject.text
    assert client.post("/nb/klasse/2/MAT01-06/quiz").status_code == 404
    assert client.get("/nb/nivatest/MAT01-06").status_code == 404
    assert client.get(READING_PATH).status_code == 404
    assert "/nivatest/" not in client.get("/nb/").text


def test_the_committed_passages_reach_a_pupil_once_approved() -> None:
    """The other half, against the real `data/reading/`: approving through the
    instance's own ledger is enough, and nothing else is needed."""
    app, client = committed_app()
    assert client.get(READING_PATH).status_code == 404

    approve_app(app)

    listing = client.get(READING_PATH)
    assert listing.status_code == 200
    assert "Venter på godkjenning" not in listing.text
    assert client.post("/nb/klasse/2/MAT01-06/quiz", follow_redirects=False).status_code == 303
