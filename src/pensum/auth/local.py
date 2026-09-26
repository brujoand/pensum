"""Administering an instance on your own machine, with no identity provider.

Content is live only once an administrator approves it on the instance, and an
administrator is normally someone the OIDC provider says is in the admin group.
A maintainer running Pensum on a laptop has no provider, and so would have no
way to approve anything and nothing to look at. This is that way, and it is
deliberately narrow.

**Every one of these must hold, on every request, or the session is refused:**

1. `PENSUM_LOCAL_ADMIN` is exactly `1`. Never on by default, and a startup
   warning is logged whenever it is set.
2. No OIDC client is configured, not even part of one. An instance meant to
   have real accounts never has a second way in.
3. The client address is loopback (`127.0.0.0/8`, `::1`).
4. The request carries none of `X-Forwarded-For`, `Forwarded` or `X-Real-IP`.
5. The request was addressed to this machine by a loopback name: its `Host` is
   `localhost`, `127.0.0.1` or `[::1]`.

Why 4 is not redundant with 3: a reverse proxy running on the same host
connects to Pensum from 127.0.0.1. To Pensum, every request it relays -- from
anywhere on the internet -- arrives from loopback. The forwarding headers are
how such a proxy says whose request it really is, and every mainstream proxy
adds at least one of them. A request that has them came through something, and
is refused. Uvicorn may rewrite the client address from `X-Forwarded-For`, but
it leaves the header in place, so the check still sees it.

Why 5: DNS rebinding. A web page on any site can point its own hostname at
127.0.0.1 and then make same-origin requests to it from the maintainer's
browser -- requests that arrive from loopback with no forwarding header. What
gives them away is the `Host` header, which still names the attacker's domain.

And why 1 is still needed with 3, 4 and 5: a proxy configured *not* to add
forwarding headers would pass them. The explicit flag is what makes that a
decision someone made on a machine they control, rather than a default that
happens to be exploitable.

The session is an ordinary signed cookie, but its own cookie with its own salt:
an OIDC login cookie can never be read as a local one or the reverse. Holding it
grants nothing by itself -- `current_user` re-checks every condition on each
request, so turning the flag off or putting a proxy in front ends every local
session at once.
"""

from __future__ import annotations

import ipaddress
from typing import Literal

from fastapi import Request

from pensum.auth.models import User
from pensum.config import Settings

# The subject every local session carries. Not a provider's `sub`, and never
# stored against a pupil: attempts are only recorded with sign-in configured,
# and sign-in configured is exactly when this is refused.
LOCAL_SUB = "local-admin"

# Lower-case, as Starlette normalises header names.
FORWARDING_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip")

Refusal = Literal["flag-off", "oidc-configured", "not-loopback", "forwarded", "foreign-host"]

# The names a request to this machine can carry in its Host header.
LOOPBACK_NAMES = frozenset({"localhost"})


def refusal(settings: Settings, request: Request) -> Refusal | None:
    """Why this request may not act as a local administrator, or None if it may.

    Checked in the order a reader would ask: is the feature on at all, then is
    this request one it could apply to.
    """
    if not settings.local_admin:
        return "flag-off"
    if settings.oidc_configured:
        return "oidc-configured"
    if not _loopback(request):
        return "not-loopback"
    if any(header in request.headers for header in FORWARDING_HEADERS):
        return "forwarded"
    if not _addressed_to_loopback(request):
        return "foreign-host"
    return None


def allowed(settings: Settings, request: Request) -> bool:
    return refusal(settings, request) is None


def _loopback(request: Request) -> bool:
    """Whether the socket peer is this machine. A missing or odd address is not."""
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _addressed_to_loopback(request: Request) -> bool:
    """Whether the Host header names this machine, rather than some domain.

    Read from the header itself rather than `request.url`, which is built from
    it and fails outright on some IPv6 forms; a header this check cannot make
    sense of is refused.
    """
    raw = request.headers.get("host", "").strip().lower()
    if raw.startswith("["):
        host = raw[1 : raw.find("]")] if "]" in raw else ""
    else:
        host = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw
    if not host:
        return False
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def local_user(settings: Settings) -> User:
    """The administrator a local session is. In the admin group by construction."""
    return User(sub=LOCAL_SUB, name="localhost", groups=(settings.admin_group,))
