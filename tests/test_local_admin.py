"""The local administrator: every way it must be refused, and the one way it is not.

A sign-in with no password, so each condition in `pensum.auth.local` gets its
own test, through the real route and the real cookie. The forwarding-header
cases are the ones that matter most: a reverse proxy on the same host connects
from loopback, and those headers are the only sign that a request came through
one.

Addresses other than loopback are from the documentation ranges (RFC 5737).
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from pensum.auth.cookies import LOCAL_COOKIE, CookieCodec
from pensum.auth.models import User
from pensum.catalogue.loader import Catalogue
from pensum.config import Settings
from pensum.items.loader import ItemBank
from pensum.web.app import create_app

SECRET = "test-secret"
LOOPBACK = ("127.0.0.1", 50000)
ELSEWHERE = ("198.51.100.5", 50000)
LOCAL_ORIGIN = "http://localhost:8000"
REVIEW_PATH = "/nb/admin/gjennomgang"

# Loaded once: the catalogue is immutable, and nothing here needs content --
# only a page behind the admin gate to knock on.
CATALOGUE = Catalogue.load()


def settings(**overrides: object) -> Settings:
    return Settings(**({"local_admin": True, "session_secret": SECRET} | overrides))


def client(
    active: Settings, address: tuple[str, int] = LOOPBACK, origin: str = LOCAL_ORIGIN
) -> TestClient:
    app = create_app(CATALOGUE, ItemBank([]), settings=active)
    return TestClient(app, base_url=origin, client=address)


def sign_in(test_client: TestClient, **headers: str):
    return test_client.post("/auth/local", headers=headers, follow_redirects=False)


# --- it works where it should ------------------------------------------------------


def test_on_loopback_with_the_flag_and_no_provider_it_grants_an_admin_session() -> None:
    test_client = client(settings())

    response = sign_in(test_client)
    assert response.status_code == 303
    assert LOCAL_COOKIE in response.cookies

    assert test_client.get(REVIEW_PATH).status_code == 200


def test_ipv6_loopback_counts() -> None:
    test_client = client(settings(), ("::1", 50000))
    assert sign_in(test_client).status_code == 303
    assert test_client.get(REVIEW_PATH).status_code == 200


def test_the_header_offers_it_only_where_it_would_work() -> None:
    assert "/auth/local" in client(settings()).get("/nb/").text
    assert "/auth/local" not in client(settings(), ELSEWHERE).get("/nb/").text
    assert "/auth/local" not in client(settings(local_admin=False)).get("/nb/").text


def test_the_session_belongs_to_that_browser_only() -> None:
    first = client(settings())
    sign_in(first)
    other = TestClient(first.app, base_url=LOCAL_ORIGIN, client=LOOPBACK)
    assert other.get(REVIEW_PATH).status_code == 401


# --- every refusal -----------------------------------------------------------------


def test_refused_when_the_flag_is_off() -> None:
    test_client = client(settings(local_admin=False))
    response = sign_in(test_client)
    assert response.status_code == 404
    assert LOCAL_COOKIE not in response.cookies
    # And with no way to be an administrator, the admin pages do not exist.
    assert test_client.get(REVIEW_PATH).status_code == 404


@pytest.mark.parametrize(
    "provider",
    [
        {
            "oidc_issuer": "https://id.example.com",
            "oidc_client_id": "pensum",
            "oidc_client_secret": "s3cret",
        },
        # Half a provider is still an instance meant to have real accounts.
        {"oidc_issuer": "https://id.example.com"},
        {"oidc_client_id": "pensum"},
        {"oidc_client_secret": "s3cret"},
    ],
)
def test_refused_when_any_oidc_provider_is_configured(provider: dict[str, str]) -> None:
    response = sign_in(client(settings(**provider)))
    assert response.status_code == 404
    assert LOCAL_COOKIE not in response.cookies


@pytest.mark.parametrize("address", [ELSEWHERE, ("192.0.2.7", 1), ("testclient", 1)])
def test_refused_from_anywhere_but_loopback(address: tuple[str, int]) -> None:
    response = sign_in(client(settings(), address))
    assert response.status_code == 403
    assert LOCAL_COOKIE not in response.cookies


@pytest.mark.parametrize(
    "header",
    [
        {"X-Forwarded-For": "203.0.113.9"},
        {"Forwarded": "for=203.0.113.9"},
        {"X-Real-IP": "203.0.113.9"},
        # Pointing at loopback is no better: the header says a proxy was there.
        {"X-Forwarded-For": "127.0.0.1"},
    ],
)
def test_refused_through_a_proxy_on_the_same_host(header: dict[str, str]) -> None:
    response = sign_in(client(settings()), **header)
    assert response.status_code == 403
    assert LOCAL_COOKIE not in response.cookies


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "[::1]:8000", "localhost", "LOCALHOST:8000"])
def test_a_loopback_name_in_the_host_header_counts(host: str) -> None:
    assert sign_in(client(settings()), host=host).status_code == 303


@pytest.mark.parametrize(
    "host", ["", "[::1", "localhost.rebound.example.com", "127.0.0.1.nip.example"]
)
def test_a_host_header_that_is_not_plainly_loopback_is_refused(host: str) -> None:
    assert sign_in(client(settings()), host=host).status_code == 403


@pytest.mark.parametrize(
    "origin", ["http://rebound.example.com:8000", "http://testserver", "http://192.0.2.7:8000"]
)
def test_refused_when_the_request_names_another_host(origin: str) -> None:
    """DNS rebinding: a page on another site points its own name at 127.0.0.1.
    The request then comes from loopback with no forwarding header, and only
    its Host header gives it away."""
    response = sign_in(client(settings(), origin=origin))
    assert response.status_code == 403
    assert LOCAL_COOKIE not in response.cookies


def test_a_session_cookie_is_worthless_under_another_host_name() -> None:
    test_client = client(settings(), origin="http://rebound.example.com:8000")
    test_client.cookies.set(LOCAL_COOKIE, local_cookie())
    assert test_client.get(REVIEW_PATH).status_code == 401


def test_a_get_cannot_start_a_session() -> None:
    """POST only: a GET would let any page open in this browser sign it in."""
    assert client(settings()).get("/auth/local").status_code == 405


# --- a session is re-checked on every request ----------------------------------------


def local_cookie(secret: str = SECRET) -> str:
    return CookieCodec(secret).dump_local()


def test_a_session_cookie_is_worthless_once_the_request_comes_through_a_proxy() -> None:
    test_client = client(settings())
    test_client.cookies.set(LOCAL_COOKIE, local_cookie())
    assert test_client.get(REVIEW_PATH).status_code == 200
    forwarded = test_client.get(REVIEW_PATH, headers={"X-Forwarded-For": "203.0.113.9"})
    assert forwarded.status_code == 401


def test_a_session_cookie_is_worthless_from_another_address() -> None:
    test_client = client(settings(), ELSEWHERE)
    test_client.cookies.set(LOCAL_COOKIE, local_cookie())
    assert test_client.get(REVIEW_PATH).status_code == 401


def test_a_session_cookie_is_worthless_once_the_flag_is_off() -> None:
    test_client = client(settings(local_admin=False))
    test_client.cookies.set(LOCAL_COOKIE, local_cookie())
    assert test_client.get(REVIEW_PATH).status_code == 404


def test_a_session_cookie_is_worthless_on_an_instance_with_a_provider() -> None:
    test_client = client(
        settings(
            oidc_issuer="https://id.example.com",
            oidc_client_id="pensum",
            oidc_client_secret="s3cret",
        )
    )
    test_client.cookies.set(LOCAL_COOKIE, local_cookie())
    assert test_client.get(REVIEW_PATH).status_code == 401


def test_a_forged_cookie_is_nothing() -> None:
    test_client = client(settings())
    test_client.cookies.set(LOCAL_COOKIE, local_cookie("another-secret"))
    assert test_client.get(REVIEW_PATH).status_code == 401


def test_a_login_cookie_cannot_be_replayed_as_a_local_one() -> None:
    login = CookieCodec(SECRET).dump_login(User(sub="x", name="x", groups=("pensum-admins",)))
    test_client = client(settings())
    test_client.cookies.set(LOCAL_COOKIE, login)
    assert test_client.get(REVIEW_PATH).status_code == 401


def test_signing_out_ends_it() -> None:
    test_client = client(settings())
    sign_in(test_client)
    test_client.post("/auth/logout", follow_redirects=False)
    assert test_client.get(REVIEW_PATH).status_code == 401


# --- it is never quiet -----------------------------------------------------------------


def test_the_flag_is_off_unless_it_is_exactly_one(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("true", "yes", "on", "0", ""):
        monkeypatch.setenv("PENSUM_LOCAL_ADMIN", value)
        assert not Settings.from_env().local_admin
    monkeypatch.setenv("PENSUM_LOCAL_ADMIN", "1")
    assert Settings.from_env().local_admin
    monkeypatch.delenv("PENSUM_LOCAL_ADMIN")
    assert not Settings.from_env().local_admin


def test_a_warning_is_logged_at_startup_when_it_is_set(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="pensum.web.app"):
        create_app(CATALOGUE, ItemBank([]), settings=settings())
    assert any("PENSUM_LOCAL_ADMIN" in r.getMessage() for r in caplog.records)


def test_the_warning_says_it_is_off_when_a_provider_is_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="pensum.web.app"):
        create_app(
            CATALOGUE,
            ItemBank([]),
            settings=settings(oidc_issuer="https://id.example.com"),
        )
    assert any("OFF" in r.getMessage() for r in caplog.records)


def test_nothing_is_logged_without_it(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="pensum.web.app"):
        create_app(CATALOGUE, ItemBank([]), settings=settings(local_admin=False))
    assert not any("PENSUM_LOCAL_ADMIN" in r.getMessage() for r in caplog.records)
