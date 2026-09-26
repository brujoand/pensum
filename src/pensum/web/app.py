"""FastAPI application factory.

The catalogue loads once at startup and is then immutable. There is no database
behind the curriculum: the whole dataset is a few megabytes of vendored JSON, and
keeping it in memory means a page load touches no network and no disk.

One SQLite database is always attached, because whether content is live is
data on the instance (`pensum.review`): with nothing approved in it, nothing is
served to a pupil. Three optional subsystems attach beside it, all off unless
configured: sign-in against an OIDC provider (which is also what turns on the
recording of finished attempts), a local administrator for a machine with no
provider (`pensum.auth.local`), and the speech models that turn a reading from
timed into checked. With none of them set -- which is what `docker run` with no
environment gives you -- this is the app that records nothing about anybody and
makes no outbound request.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pensum import __version__
from pensum.auth.cookies import CookieCodec
from pensum.auth.oidc import OidcClient
from pensum.catalogue.loader import Catalogue
from pensum.config import Settings
from pensum.config import settings as env_settings
from pensum.items.loader import ItemBank
from pensum.listening.library import ListeningLibrary
from pensum.quiz.session import SessionStore
from pensum.reading.library import ReadingLibrary
from pensum.reading.streams import StreamStore
from pensum.reading.transcribe import Transcriber, load_transcriber
from pensum.review.store import ReviewLedger, ReviewStore
from pensum.scores.evidence import EvidenceStore
from pensum.scores.store import AttemptStore
from pensum.skills.loader import SkillLibrary
from pensum.web.admin_routes import router as admin_router
from pensum.web.auth_routes import router as auth_router
from pensum.web.comfort_routes import router as comfort_router
from pensum.web.listening_routes import router as listening_router
from pensum.web.mastery_routes import router as mastery_router
from pensum.web.missions_routes import router as missions_router
from pensum.web.placement_routes import router as placement_router
from pensum.web.quiz_routes import router as quiz_router
from pensum.web.reading_routes import router as reading_router
from pensum.web.review_routes import router as review_router
from pensum.web.routes import router
from pensum.web.skills_routes import router as skills_router
from pensum.web.writing_routes import router as writing_router
from pensum.writing.library import WritingLibrary

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.catalogue = Catalogue.load()
    ledger = app.state.reviews
    app.state.items = ItemBank.load().with_ledger(ledger)
    if getattr(app.state, "reading", None) is None:
        app.state.reading = ReadingLibrary.load().with_ledger(ledger)
    if getattr(app.state, "writing", None) is None:
        app.state.writing = WritingLibrary.load().with_ledger(ledger)
    # Derived from the two above rather than loaded: the listening exercise has
    # no content of its own. Building it here keeps the first request off the
    # cost of reading every passage and every item back out again.
    app.state.listening = ListeningLibrary.of(app.state.items, app.state.reading)
    if getattr(app.state, "skills", None) is None:
        app.state.skills = SkillLibrary.load().with_ledger(ledger)
    yield


def create_app(
    catalogue: Catalogue | None = None,
    items: ItemBank | None = None,
    settings: Settings | None = None,
    reading: ReadingLibrary | None = None,
    writing: WritingLibrary | None = None,
    transcriber: Transcriber | None = None,
    skills: SkillLibrary | None = None,
) -> FastAPI:
    """Build the app. Pass the collaborators to substitute them in tests."""
    active = settings if settings is not None else env_settings

    app = FastAPI(
        title="Pensum",
        version=__version__,
        lifespan=lifespan if catalogue is None else None,
        # No API consumers, and the docs would only expose internals.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = active
    _warn_about_local_admin(active)
    # Built before the libraries, because each of them is handed the ledger. A
    # library with no ledger approves nothing, which is safe and therefore an
    # ordering mistake that would show up only as an empty site.
    #
    # Always built: there is always a database. Neither touches the file until
    # the first request asks something, so building the module-level `app`
    # below at import time creates nothing on disk.
    app.state.review_store = ReviewStore(active.database_file)
    app.state.reviews = ReviewLedger(app.state.review_store)

    if catalogue is not None:
        app.state.catalogue = catalogue
        app.state.items = (items if items is not None else ItemBank.load()).with_ledger(
            app.state.reviews
        )
        app.state.reading = (reading if reading is not None else ReadingLibrary.load()).with_ledger(
            app.state.reviews
        )
        app.state.writing = (writing if writing is not None else WritingLibrary.load()).with_ledger(
            app.state.reviews
        )
        app.state.listening = ListeningLibrary.of(app.state.items, app.state.reading)
        app.state.skills = (skills if skills is not None else SkillLibrary.load()).with_ledger(
            app.state.reviews
        )
    else:
        # The lifespan builds the rest and attaches the ledger there. Only what
        # was injected has to be wired up here; None means the lifespan loads
        # it, as it does the item bank.
        app.state.reading = reading.with_ledger(app.state.reviews) if reading is not None else None
        app.state.writing = writing.with_ledger(app.state.reviews) if writing is not None else None
        app.state.skills = skills.with_ledger(app.state.reviews) if skills is not None else None

    # Loaded here rather than in the lifespan so a test can inject a fake
    # without a model on disk. None -- no models configured -- is the default
    # and is an ordinary state: readings are then timed but not checked.
    app.state.transcriber = (
        transcriber if transcriber is not None else load_transcriber(active.speech_model_dir)
    )

    # Quiz sessions live here rather than in a store: an unfinished quiz is not
    # a result, so a restart losing in-flight quizzes is the accepted cost.
    app.state.sessions = SessionStore()

    # Readings in progress, held only while they are in progress. Same trade as
    # quiz sessions: a restart loses an in-flight reading, which is not a result.
    app.state.streams = StreamStore()

    app.state.cookies = CookieCodec(active.session_secret)
    # Constructed eagerly so half-configured sign-in fails at startup rather
    # than on the first child who clicks it. Discovery stays lazy -- the
    # provider does not have to be up before Pensum is.
    app.state.oidc = OidcClient(active) if active.auth_enabled else None
    app.state.attempts = AttemptStore(active.database_file) if active.history_enabled else None
    # Same gate and same file as the attempts: evidence is written alongside a
    # finished attempt and never otherwise. See `pensum.scores.evidence`.
    app.state.evidence = EvidenceStore(active.database_file) if active.history_enabled else None

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    app.include_router(quiz_router)
    app.include_router(placement_router)
    app.include_router(reading_router)
    app.include_router(writing_router)
    app.include_router(listening_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(review_router)
    app.include_router(skills_router)
    app.include_router(comfort_router)
    app.include_router(missions_router)
    app.include_router(mastery_router)
    return app


def _warn_about_local_admin(settings: Settings) -> None:
    """Say, at startup and in the log, that the local-admin switch is set.

    It is a development switch with a security consequence, so it should never
    be on quietly: whoever reads the log of an instance that has it is told,
    and told whether it is actually in effect.
    """
    if not settings.local_admin:
        return
    if settings.oidc_configured:
        logger.warning(
            "PENSUM_LOCAL_ADMIN=1 is set but an OIDC client is configured; "
            "local administration is OFF. Unset PENSUM_LOCAL_ADMIN."
        )
        return
    logger.warning(
        "PENSUM_LOCAL_ADMIN=1: a browser on this machine (loopback, no forwarding "
        "headers) can sign in as an administrator without a password. For "
        "development only; never set this on an instance anyone else can reach."
    )


app = create_app()
