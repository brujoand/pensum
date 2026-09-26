# Single stage: there is no build step to isolate. No JS toolchain, no compiled
# assets, and the curriculum is baked in as data.
FROM python:3.13-slim

# uv from the official image rather than pip-installed, so the version is pinned
# by digest rather than by whatever pip resolves at build time.
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Speech-to-text for the reading exercise. Off by default: it adds CTranslate2
# and its dependencies to the image, and it is useless without a model
# directory, which is a mount rather than a layer -- the models are hundreds of
# megabytes and are not ours to redistribute. See bin/fetch_speech_models.
#
#   docker build --build-arg WITH_SPEECH=1 .
ARG WITH_SPEECH=0

# Dependencies before source, so a code change does not re-resolve them.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN if [ "${WITH_SPEECH}" = "1" ]; then \
      uv sync --frozen --no-dev --no-install-project --extra speech; \
    else \
      uv sync --frozen --no-dev --no-install-project; \
    fi

COPY src/ ./src/
COPY data/curriculum/ ./data/curriculum/
COPY data/items/ ./data/items/
COPY data/reading/ ./data/reading/
COPY data/writing/ ./data/writing/
RUN if [ "${WITH_SPEECH}" = "1" ]; then \
      uv sync --frozen --no-dev --extra speech; \
    else \
      uv sync --frozen --no-dev; \
    fi

# Non-root, and a fixed uid so a read-only root filesystem or a restrictive
# PodSecurityContext has something predictable to point at.
#
# data/instance is where the database goes when PENSUM_DATABASE_PATH is unset.
# Created here, owned by that uid, so a named volume mounted on it starts out
# writable; without a volume it lives and dies with the container.
RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin pensum \
    && mkdir -p /app/data/instance \
    && chown -R pensum:pensum /app
USER 65532

# The same version the image is TAGGED with, so the tag in the registry and the
# version the app reports come from one source.
ARG VERSION=dev
ENV APP_VERSION=${VERSION}

EXPOSE 8000

# No secrets and no network egress with an empty environment, which is how this
# image is meant to be run. It always keeps a small SQLite database -- review
# decisions are what make content visible to pupils -- at
# /app/data/instance/pensum.db unless PENSUM_DATABASE_PATH says otherwise; mount
# a volume there to keep it. Sign-in and speech checking are opt-in: they add an
# OIDC client secret and a read-only model mount respectively -- see the README. Speech checking runs against a
# local model and makes no outbound request either. If this container ever needs
# an API key to serve a quiz, something has gone wrong upstream of here.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"

# The venv binary directly, not `uv run`: uv would re-check the lockfile at
# container start, which is a resolution step -- and potentially a network call
# -- on a path that should do nothing but exec the server.
CMD ["/app/.venv/bin/uvicorn", "pensum.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
