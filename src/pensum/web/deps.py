"""What routes reach for: settings, the signed-in user, the admin gate.

All of it hangs off `app.state`, set once in the factory, so a test can build an
app with sign-in configured without touching the environment.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from pensum.auth import local
from pensum.auth.cookies import CookieCodec, read_local, read_user
from pensum.auth.models import User
from pensum.auth.oidc import OidcClient
from pensum.config import Settings
from pensum.missions.loader import MissionLibrary
from pensum.review.store import Kind, ReviewLedger, ReviewStore, State
from pensum.scores.evidence import EvidenceStore
from pensum.scores.store import AttemptStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_codec(request: Request) -> CookieCodec:
    return request.app.state.cookies


def get_oidc(request: Request) -> OidcClient | None:
    return request.app.state.oidc


def get_store(request: Request) -> AttemptStore | None:
    return request.app.state.attempts


def get_evidence(request: Request) -> EvidenceStore | None:
    """Where evidence rows go. None exactly when `get_store` is None."""
    return request.app.state.evidence


def get_review_store(request: Request) -> ReviewStore:
    """Where review decisions are written. There is always a database."""
    return request.app.state.review_store


def get_reviews(request: Request) -> ReviewLedger:
    """The decisions the content libraries are already consulting.

    The same object they hold, not a copy: reloading it after a write is what
    makes an approval take effect on the next page load rather than in half a
    minute.
    """
    return request.app.state.reviews


def get_missions(request: Request) -> MissionLibrary:
    """The missions, loaded on first use and kept on the app.

    Loaded here rather than in the app's lifespan so that a test can put its
    own library on `app.state.missions` before the first request. Whichever it
    is, it answers to this instance's review decisions.
    """
    missions = getattr(request.app.state, "missions", None)
    if missions is None:
        missions = MissionLibrary.load()
        request.app.state.missions = missions
    if not missions.has_ledger:
        missions.with_ledger(get_reviews(request))
    return missions


def review_state(request: Request, kind: Kind, content_id: str) -> State:
    """Where one piece of content stands on this instance, whatever its kind.

    For the templates, which label everything an administrator is shown that a
    pupil would not be. Each library answers for its own kind; this only picks
    the library.
    """
    state = request.app.state
    if kind == "item":
        return state.items.review_state(content_id)
    if kind == "reading":
        return state.reading.review_state(content_id)
    if kind == "writing":
        return state.writing.review_state(content_id)
    if kind == "skill":
        return state.skills.review_state(content_id)
    return get_missions(request).review_state(content_id)


def current_user(request: Request) -> User | None:
    """The signed-in user, or None -- which is an ordinary state, not an error.

    Two ways to be signed in, never both on one instance: a provider login when
    OIDC is configured, or a local administrator session when it is not and
    `pensum.auth.local` lets this request have one. The local check runs on
    every request, not only at sign-in, so a session cookie outlives none of
    the conditions it was granted under.
    """
    settings = get_settings(request)
    if settings.auth_enabled:
        return read_user(request, get_codec(request))
    if read_local(request, get_codec(request)) and local.allowed(settings, request):
        return local.local_user(settings)
    return None


def admin_possible(request: Request) -> bool:
    """Whether this instance has any way for anybody to be an administrator."""
    settings = get_settings(request)
    return settings.auth_enabled or settings.local_admin_enabled


def require_admin(request: Request) -> User:
    """The gate on every admin page.

    Group membership is re-read from the cookie on each request, and the cookie
    was written from what the provider asserted at sign-in. So revoking someone
    in pocket-id takes effect when their session expires, not instantly -- which
    is the cost of not calling the provider on every page load, and is stated
    here rather than discovered later.

    With no provider, the only administrator there can be is a local one, and
    only where `pensum.auth.local` allows it. Anywhere else these pages do not
    exist.
    """
    settings = get_settings(request)
    if not admin_possible(request):
        raise HTTPException(status_code=404, detail="sign-in is not configured")

    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="sign in to view this page")
    if not user.in_group(settings.admin_group):
        raise HTTPException(status_code=403, detail="not an administrator")
    return user


def is_admin(request: Request) -> bool:
    """Whether this request comes from someone in the configured admin group."""
    settings = get_settings(request)
    user = current_user(request)
    return user is not None and user.in_group(settings.admin_group)


def sees_unreviewed(request: Request) -> bool:
    """Whether this request may be shown content that is not approved here.

    Only an administrator, and only per request: content has to be met in
    place -- in its own quiz, reading page or tracing page -- before anyone can
    decide whether it is fit, and signing in is the only way to establish who
    is asking. Everything such a reader sees that a pupil would not is labelled
    with its state.

    There is no deployment-wide switch. An instance shows pupils what its
    administrators approved, and nothing else, whatever its environment says.
    """
    return is_admin(request)


def base_url(request: Request) -> str:
    """Pensum's own public origin.

    Behind a TLS-terminating proxy the request scheme is http, and a redirect
    URI built from it would not match the one registered with the provider.
    `PENSUM_BASE_URL` is the override for exactly that, and it wins when set.
    """
    configured = get_settings(request).base_url
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def is_secure(request: Request) -> bool:
    """Whether to mark cookies Secure. Derived, so local http still works."""
    return base_url(request).startswith("https://")


def safe_next(candidate: str | None, fallback: str) -> str:
    """Only ever redirect to a path on this site.

    `?next=` is attacker-controlled by definition. A value starting with `//`
    is a protocol-relative URL to another host and is refused along with
    anything carrying a scheme.
    """
    if not candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    return candidate
