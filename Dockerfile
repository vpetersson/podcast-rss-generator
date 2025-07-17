FROM python:3.11-slim

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy your script and requirements file
COPY rss_generator.py /rss_generator.py
COPY requirements.txt /requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /requirements.txt

# Set the entrypoint to your script
ENTRYPOINT ["python", "/rss_generator.py"]
