FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy project files
WORKDIR /app
COPY . /app/

# Install dependencies using Poetry
RUN poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# Set the entrypoint script
ENTRYPOINT ["python", "-m", "podcast_rss_generator.cli"]
