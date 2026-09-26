"""The comfort profile: the cookie, the settings page, and what they change.

The cookie is read on every page, from a value any browser extension or curious
child can edit, so the parser is tested hardest on what it refuses. The
stylesheet check is the other half of the promise: "calm" means nothing moves
anywhere on the site, and the only way to keep that true as the site grows is to
check every animation in the stylesheet rather than the ones that exist today.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from review_helpers import approve_app

from pensum.catalogue.loader import Catalogue
from pensum.i18n import UI_LOCALES, catalog
from pensum.web.app import create_app as _create_app
from pensum.web.comfort import COMFORT_COOKIE, ComfortProfile


def create_app(*args, **kwargs):
    """An app on an instance where an administrator has approved everything.

    Review is not what this module tests, so its pages serve the committed
    content the way an instance does once somebody has done the reviewing.
    """
    app = _create_app(*args, **kwargs)
    approve_app(app)
    return app


ROOT = Path(__file__).parents[1]
WEB = ROOT / "src" / "pensum" / "web"
CSS = WEB / "static" / "pensum.css"
JS_HARNESSES = [
    ROOT / "tests" / "js" / "reading_week.test.js",
    ROOT / "tests" / "js" / "comfort_voice.test.js",
]


@pytest.fixture(scope="module")
def app():
    return create_app(Catalogue.load())


@pytest.fixture
def client(app) -> TestClient:
    """A fresh cookie jar per test: a saved setting must not leak into the next
    test's "first visit"."""
    return TestClient(app)


def with_cookie(client: TestClient, profile: ComfortProfile | str) -> TestClient:
    value = profile if isinstance(profile, str) else profile.serialise()
    client.cookies.set(COMFORT_COOKIE, value)
    return client


def html_tag(page: str) -> str:
    match = re.search(r"<html\b[^>]*>", page)
    assert match, "no <html> tag"
    return match.group(0)


# --- the cookie ------------------------------------------------------------


def test_defaults_are_the_first_visit() -> None:
    profile = ComfortProfile.parse(None)
    assert profile.calm is True
    assert profile.read_aloud is False
    assert profile.bigger_targets is False
    assert profile.theme == "plain"
    assert profile.break_reminder is False


def test_round_trip() -> None:
    chosen = ComfortProfile(
        calm=False, read_aloud=True, bigger_targets=True, theme="space", break_reminder=True
    )
    assert ComfortProfile.parse(chosen.serialise()) == chosen


def test_serialised_value_needs_no_cookie_quoting() -> None:
    """Letters, digits, `_`, `:` and `|` only, so no library wraps it in quotes."""
    value = ComfortProfile(theme="vehicles").serialise()
    assert re.fullmatch(r"[A-Za-z0-9_:|]+", value)


@pytest.mark.parametrize(
    "raw",
    ["", "garbage", "{}", ";;;", "calm", "calm:yes|theme:dragons", "|||:::", "calm:2", "é:1"],
)
def test_garbage_reads_as_defaults(raw: str) -> None:
    assert ComfortProfile.parse(raw) == ComfortProfile()


def test_unknown_keys_are_ignored_and_known_ones_kept() -> None:
    profile = ComfortProfile.parse("volume:11|read_aloud:1|colour:red|theme:blocks")
    assert profile.read_aloud is True
    assert profile.theme == "blocks"
    assert profile.calm is True


def test_one_bad_value_does_not_cost_the_others() -> None:
    profile = ComfortProfile.parse("calm:0|bigger_targets:maybe|theme:animals")
    assert profile.calm is False
    assert profile.bigger_targets is False
    assert profile.theme == "animals"


# --- the settings page -----------------------------------------------------


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_settings_page_renders_as_a_plain_form(client: TestClient, locale: str) -> None:
    response = client.get(f"/{locale}/innstillinger")
    assert response.status_code == 200
    page = response.text
    assert catalog(locale)["comfort.heading"] in page
    assert f'method="post" action="/{locale}/innstillinger"' in page
    # Calm is the one setting on by default, and the form says so.
    assert re.search(r'name="calm" value="1"[^>]*checked', page, re.S)
    assert not re.search(r'name="read_aloud" value="1"[^>]*checked', page, re.S)
    assert re.search(r'name="theme" value="plain"\s*checked', page)
    assert catalog(locale)["comfort.storage"].split()[0] in page


@pytest.mark.parametrize("locale", UI_LOCALES)
def test_saving_sets_the_cookie_and_comes_back(client: TestClient, locale: str) -> None:
    response = client.post(
        f"/{locale}/innstillinger",
        data={"read_aloud": "1", "bigger_targets": "1", "theme": "space", "next": f"/{locale}/"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/{locale}/innstillinger?saved=1")
    header = response.headers["set-cookie"]
    assert header.startswith(f"{COMFORT_COOKIE}=")
    assert "HttpOnly" in header
    assert "samesite=lax" in header.lower()

    # Calm was not sent, which is what unticking it looks like.
    saved = ComfortProfile.parse(response.cookies[COMFORT_COOKIE])
    assert saved == ComfortProfile(
        calm=False, read_aloud=True, bigger_targets=True, theme="space", break_reminder=False
    )

    landed = client.get(response.headers["location"])
    assert catalog(locale)["comfort.saved"] in landed.text
    assert f'href="/{locale}/"' in landed.text


def test_an_unknown_theme_is_stored_as_plain(client: TestClient) -> None:
    response = client.post(
        "/nb/innstillinger", data={"calm": "1", "theme": "dragons"}, follow_redirects=False
    )
    assert ComfortProfile.parse(response.cookies[COMFORT_COOKIE]).theme == "plain"


def test_next_cannot_leave_the_site(client: TestClient) -> None:
    response = client.post(
        "/nb/innstillinger", data={"next": "//evil.example/"}, follow_redirects=False
    )
    assert "evil" not in response.headers["location"]


def test_every_page_links_to_the_settings(client: TestClient) -> None:
    for path in ("/nb/", "/en/", "/nb/rettigheter", "/en/klasse/3"):
        locale = path.split("/")[1]
        assert f'href="/{locale}/innstillinger?next=' in client.get(path).text


def test_no_diagnosis_is_named_anywhere() -> None:
    words = ("adhd", "autis", "dyslek", "dyslex", "diagnos", "asperger", "add ")
    for locale in UI_LOCALES:
        for key, text in catalog(locale).items():
            if key.startswith(("comfort.", "nav.comfort")):
                assert not any(w in text.lower() for w in words), key
    page = (WEB / "templates" / "pages" / "comfort.html").read_text(encoding="utf-8").lower()
    assert not any(w in page for w in ("adhd", "autis", "dyslek", "dyslex", "diagnos"))


# --- the attributes on <html> ----------------------------------------------


def test_first_visit_is_calm_and_nothing_else(client: TestClient) -> None:
    tag = html_tag(client.get("/nb/").text)
    assert "data-calm" in tag
    assert "data-bigger-targets" not in tag
    assert "data-read-aloud" not in tag
    assert 'data-theme="plain"' in tag


def test_saved_settings_reach_the_root_element(client: TestClient) -> None:
    chosen = ComfortProfile(calm=False, read_aloud=True, bigger_targets=True, theme="animals")
    page = with_cookie(client, chosen).get("/en/").text
    tag = html_tag(page)
    assert "data-calm" not in tag
    assert "data-bigger-targets" in tag
    assert "data-read-aloud" in tag
    assert 'data-speak-label="Read aloud"' in tag
    assert 'data-theme="animals"' in tag
    assert '<script src="/static/comfort.js"' in page


def test_the_script_is_only_loaded_when_asked_for(client: TestClient) -> None:
    assert "comfort.js" not in client.get("/nb/").text


def test_a_garbage_cookie_renders_the_defaults(client: TestClient) -> None:
    tag = html_tag(with_cookie(client, "calm:x|a:cookie|theme:").get("/nb/").text)
    assert "data-calm" in tag
    assert 'data-theme="plain"' in tag


# --- calm, checked against the whole stylesheet ----------------------------


def _rules(css: str) -> list[tuple[tuple[str, ...], str, str]]:
    """(enclosing at-rules, selector, body) for every rule with declarations.

    A brace parser rather than a regex, because the interesting rules sit inside
    `@media` blocks and a flat pattern would misattribute them.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: list[tuple[tuple[str, ...], str, str]] = []
    stack: list[str] = []
    start = 0
    for i, char in enumerate(css):
        if char == "{":
            stack.append(css[start:i].strip())
            start = i + 1
        elif char == "}":
            body = css[start:i]
            prelude = stack.pop() if stack else ""
            if ":" in body and not prelude.startswith("@"):
                found.append((tuple(stack), " ".join(prelude.split()), body))
            start = i + 1
    return found


def _motion(body: str) -> list[str]:
    return [
        " ".join(d.split())
        for d in body.split(";")
        if re.match(r"\s*(animation|transition)(-[a-z-]+)?\s*:", d)
    ]


CALM = ":root[data-calm] *, :root[data-calm] *::before, :root[data-calm] *::after"
REDUCED = "*, *::before, *::after"


def _neutraliser(rules, at: tuple[str, ...], selector: str) -> list[str]:
    matches = [body for context, sel, body in rules if context == at and sel == selector]
    assert matches, f"no rule for {selector!r} in {at or 'the top level'}"
    return _motion(matches[0])


@pytest.mark.parametrize(
    ("at", "selector"),
    [((), CALM), (("@media (prefers-reduced-motion: reduce)",), REDUCED)],
)
def test_calm_neutralises_every_animation(at: tuple[str, ...], selector: str) -> None:
    rules = _rules(CSS.read_text(encoding="utf-8"))
    declarations = _neutraliser(rules, at, selector)
    assert "animation: none !important" in declarations
    [transition] = [d for d in declarations if d.startswith("transition")]
    match = re.fullmatch(r"transition: opacity (\d+)ms [a-z-]+ !important", transition)
    assert match, transition
    assert int(match.group(1)) <= 150


def test_no_other_motion_rule_can_outrank_calm() -> None:
    """The universal rule wins because it is `!important`. Anything else carrying
    `!important` on a motion property would win back -- so nothing may."""
    rules = _rules(CSS.read_text(encoding="utf-8"))
    others = [
        (sel, d)
        for context, sel, body in rules
        if sel not in (CALM, REDUCED)
        for d in _motion(body)
    ]
    # There are animations on the site; if this ever finds none, the parser broke.
    assert any(d.startswith("animation") for _, d in others)
    assert any(d.startswith("transition") for _, d in others)
    assert not [(s, d) for s, d in others if "!important" in d]


def test_no_template_or_script_animates_inline() -> None:
    """An inline `!important` would beat the stylesheet, so none is allowed; and
    an inline animation is one this test cannot see, so none of those either."""
    inline = re.compile(r"style=\"[^\"]*(animation|transition)|\.style\.(animation|transition)")
    for path in [*(WEB / "templates").rglob("*.html"), *(WEB / "static").glob("*.js")]:
        if path.name == "htmx.min.js":
            continue
        assert not inline.search(path.read_text(encoding="utf-8")), path


# --- the browser halves ----------------------------------------------------


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("harness", JS_HARNESSES, ids=lambda p: p.name)
def test_js_harness(harness: Path) -> None:
    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", str(harness)],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_harnesses_are_reachable() -> None:
    """Node is not a dependency, so the check above skips where it is missing --
    including, silently, if a harness is deleted. This one does not skip."""
    for harness in JS_HARNESSES:
        assert harness.is_file()
