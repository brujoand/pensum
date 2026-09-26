"""Runtime configuration.

Everything has a working default. The container must start with no environment
set at all, and when it does it has no sign-in and records nothing about anyone.

**There is always a database.** Whether a piece of content is live is data on
the instance (`pensum.review`), so the instance needs somewhere to keep it even
when nobody signs in. `PENSUM_DATABASE_PATH` names the file; unset, it is
`DEFAULT_DATABASE_PATH`, inside the app's own data directory. In a container
that path is inside the container, so without a volume mounted there the
review decisions -- and with them everything pupils can see -- are lost when the
container is replaced. The README says so where it shows the `docker run` line.

Two optional subsystems change what is recorded, and both are off unless
explicitly configured:

* **Sign-in** turns on when an OIDC issuer, client id and client secret are all
  present. Signing in is never required -- an anonymous pupil gets the same quiz
  and is still not recorded.
* **Score history** follows sign-in: only attempts by a signed-in pupil are ever
  written, into the same database.

And one that exists only for a maintainer's own machine: `PENSUM_LOCAL_ADMIN=1`
(see `pensum.auth.local`), which lets a browser on the same machine act as an
administrator when no identity provider is configured at all.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where the database lives when nothing says otherwise: `data/instance/` in a
# checkout, `/app/data/instance/` in the image. Its own directory, so that a
# volume can be mounted on it without hiding the curriculum and content that
# sit beside it in `data/`, and so that `.gitignore` can name it.
DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "instance" / "pensum.db"


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _text(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip() or None


@dataclass(frozen=True)
class Settings:
    """Settings read once at startup."""

    # --- Reading fluency ----------------------------------------------------
    # Where the CTranslate2 Whisper models live -- either one model per
    # language in "nb"/"en" subdirectories, or a single multilingual model at
    # this path. Unset -- the default, and what the published image ships with
    # -- means the reading page still shows the passage and times the reading,
    # but nothing is transcribed and no accuracy is reported. The models are
    # hundreds of megabytes and are not ours to redistribute, so they are
    # fetched rather than committed: see bin/fetch_speech_models.
    speech_model_dir: Path | None = None

    # Whether to light words up while the pupil is still reading. Costs real
    # CPU: a window of recent audio is transcribed every couple of seconds, on
    # top of the single pass at the end that produces the score. Worth it on a
    # machine serving a household, and the first thing to turn off on one
    # serving a school. Ignored entirely when no models are configured.
    speech_live: bool = True

    # Whether the page may offer the browser's own speech recogniser. On when
    # available, because on a phone it is usually better at children than the
    # server models are and -- where the browser can do it on-device -- more
    # private than posting the audio here. The page refuses to use a cloud
    # recogniser without an explicit opt-in; this switch turns the whole offer
    # off for a deployment that would rather not have the conversation.
    device_speech: bool = True

    # --- Rights and takedowns -----------------------------------------------
    # Where a rights holder writes if they believe something here is theirs.
    # Everything Pensum serves is either Udir's under NLOD or written for
    # Pensum, so this address should never receive anything -- which is exactly
    # why it has to be published: a contact that only matters when we are wrong
    # is worthless if it appears only after we are.
    #
    # Configurable so a fork gets its own inbox rather than ours.
    dmca_email: str = "dmca@brujordet.no"

    # --- Sign-in (pocket-id, or any OIDC provider) --------------------------
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None

    # The group a pocket-id account must be in to read other people's scores.
    # Membership is managed in pocket-id, not here, so granting or revoking
    # admin never means redeploying Pensum.
    admin_group: str = "pensum-admins"

    # Pensum's own public origin, used to build the redirect URI. Derived from
    # the incoming request when unset, which is right for a direct deployment
    # and wrong behind a proxy that terminates TLS -- hence the override.
    base_url: str | None = None

    # Signs the login cookie. Generated per process when unset, so a restart
    # silently signs everyone out. That is the right default for a secret we
    # would otherwise have to invent: losing a session is an inconvenience, a
    # predictable signing key is not.
    session_secret: str = ""

    # --- The database -------------------------------------------------------
    # Review decisions always; attempts and evidence too once sign-in is on.
    # None means `DEFAULT_DATABASE_PATH` -- read through `database_file`, never
    # directly, so there is one place that knows the default.
    database_path: Path | None = None

    # --- Local administration, for a machine with no identity provider -------
    # Off unless PENSUM_LOCAL_ADMIN is exactly "1". Even then it is honoured
    # only with no OIDC client configured, and only for a request from a
    # loopback address carrying no forwarding header -- see
    # `pensum.auth.local` for why each of those is required.
    local_admin: bool = False

    @property
    def speech_enabled(self) -> bool:
        """Whether a recording can be checked, as opposed to merely timed.

        Only says a directory was configured and exists; whether vosk is
        importable and a model actually loads is settled in
        `pensum.reading.transcribe.load_transcriber`, which degrades to None.
        """
        return self.speech_model_dir is not None and self.speech_model_dir.is_dir()

    @property
    def auth_enabled(self) -> bool:
        """Sign-in needs all three halves of an OIDC client to work at all."""
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

    @property
    def oidc_configured(self) -> bool:
        """Whether any part of an OIDC client is set, even an incomplete one.

        Distinct from `auth_enabled` on purpose: local administration must stay
        off on an instance where someone *tried* to configure a provider and
        got one value wrong, because that instance is meant to have real
        accounts and is merely broken.
        """
        return bool(self.oidc_issuer or self.oidc_client_id or self.oidc_client_secret)

    @property
    def local_admin_enabled(self) -> bool:
        """The flag is set and no provider is configured. Per-request checks still apply."""
        return self.local_admin and not self.oidc_configured

    @property
    def database_file(self) -> Path:
        """The SQLite file this instance keeps its data in. Always one."""
        return self.database_path if self.database_path is not None else DEFAULT_DATABASE_PATH

    @property
    def history_enabled(self) -> bool:
        """Recording a score needs a name to put on it; the database always exists."""
        return self.auth_enabled

    @classmethod
    def from_env(cls) -> Settings:
        database = _text("PENSUM_DATABASE_PATH")
        speech_models = _text("PENSUM_SPEECH_MODEL_DIR")
        issuer = _text("PENSUM_OIDC_ISSUER")
        base_url = _text("PENSUM_BASE_URL")
        return cls(
            speech_model_dir=Path(speech_models) if speech_models else None,
            speech_live=_flag("PENSUM_SPEECH_LIVE", default=True),
            device_speech=_flag("PENSUM_DEVICE_SPEECH", default=True),
            dmca_email=_text("PENSUM_DMCA_EMAIL") or "dmca@brujordet.no",
            # Trailing slashes matter: the issuer is concatenated with the
            # discovery path, and `aud`/`iss` comparisons are exact.
            oidc_issuer=issuer.rstrip("/") if issuer else None,
            oidc_client_id=_text("PENSUM_OIDC_CLIENT_ID"),
            oidc_client_secret=_text("PENSUM_OIDC_CLIENT_SECRET"),
            admin_group=_text("PENSUM_ADMIN_GROUP") or "pensum-admins",
            base_url=base_url.rstrip("/") if base_url else None,
            session_secret=_text("PENSUM_SESSION_SECRET") or secrets.token_urlsafe(32),
            database_path=Path(database) if database else None,
            # Exactly "1", not any truthy spelling: this one is a security
            # switch, and it should take a deliberate act to turn on.
            local_admin=os.environ.get("PENSUM_LOCAL_ADMIN") == "1",
        )


settings = Settings.from_env()
