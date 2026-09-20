# Build stage: resolve dependencies from the lockfile and install the project
# itself into a self-contained virtualenv. Nothing from this stage ships
# except /app/.venv.
FROM python:3.11-slim AS builder

# uv comes from its official image rather than a curl | sh step, so the
# version is pinned and reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so this layer stays cached until the lockfile changes.
# --frozen fails rather than silently re-resolving if uv.lock is stale.
# --no-dev omits mypy, ruff, pytest and yamllint, which the image does not need.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-editable

# Then the source, and the project itself. --no-editable builds and installs a
# real wheel into the virtualenv rather than linking back to /app/src, which
# is what lets the runtime stage ship the virtualenv alone: the image runs the
# packaged distribution, exactly what `pip install podcast-rss-generator`
# would give a user.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


# Runtime stage: ffmpeg plus the prebuilt virtualenv. Neither uv nor the
# source tree is needed at runtime, so both stay behind in the builder.
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /data

COPY --from=builder /app/.venv /app/.venv

# Put the virtualenv first so the console script resolves without activation.
ENV PATH="/app/.venv/bin:$PATH"

# The console script declared in [project.scripts], not a path into a source
# tree: the entry point is part of the package's contract and is covered by
# tests/test_packaging.py.
ENTRYPOINT ["podcast-rss-generator"]
