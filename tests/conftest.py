"""Shared test configuration.

The suite must never reach the network. Udir is a public service with no SLA, and
a test that quietly depends on it turns their maintenance window into our red
build -- while also being slow and non-deterministic for everyone.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import pensum.config


@pytest.fixture(autouse=True)
def no_outbound_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a real HTTP connection.

    Blocks httpx's real transports only. `ASGITransport` is a different class and
    keeps working, so `TestClient` still drives the app in-process -- which is
    the distinction that matters: exercising our own routes is fine, leaving the
    machine is not.
    """

    def refuse(self: object, *args: object, **kwargs: object) -> None:
        raise RuntimeError("a test attempted a real HTTP request; use recorded fixtures instead")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


@pytest.fixture(scope="module", autouse=True)
def module_default_database(tmp_path_factory: pytest.TempPathFactory):
    """The same redirect for a module-scoped app, which is built before any
    function-scoped fixture runs. Per module, so one module's approvals are
    never served in the next."""
    path = tmp_path_factory.mktemp("module-default") / "pensum.db"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pensum.config, "DEFAULT_DATABASE_PATH", path)
        yield path


@pytest.fixture(autouse=True)
def default_database_in_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the default database at this test's own directory.

    There is always a database (`pensum.config`), and an app built without a
    `database_path` uses the default one -- which in a checkout is a file under
    `data/instance/`. Without this every such test would share that file, and a
    decision one test recorded would be served in the next -- and the suite
    would write into the checkout.
    """
    path = tmp_path / "default" / "pensum.db"
    monkeypatch.setattr(pensum.config, "DEFAULT_DATABASE_PATH", path)
    return path
