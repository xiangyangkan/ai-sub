FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir . \
    && playwright install chromium \
    && playwright install-deps chromium

VOLUME /app/data

CMD ["python", "-m", "ai_sub.main"]
