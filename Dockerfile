# Build stage: resolve dependencies from the lockfile into a self-contained
# virtualenv. Nothing from this stage ships except /app/.venv.
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
# --no-dev omits mypy, ruff and yamllint, which the image does not need.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY rss_generator.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# Runtime stage: ffmpeg plus the prebuilt virtualenv. uv is not needed at
# runtime, so it stays behind in the builder.
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY rss_generator.py ./

# Put the virtualenv first so `python` resolves to it without activation.
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "/app/rss_generator.py"]
