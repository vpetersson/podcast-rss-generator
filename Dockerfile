FROM python:3.12-slim-bookworm

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy only necessary files for dependency installation
WORKDIR /app
COPY pyproject.toml README.md LICENSE /app/

# Generate poetry.lock file with Python 3.13
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# Copy the rest of the project files
COPY . /app/

# Set the entrypoint script
ENTRYPOINT ["python", "-m", "podcast_rss_generator.cli"]
