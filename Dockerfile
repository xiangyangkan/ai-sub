FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN pip install --no-cache-dir .

VOLUME /app/data

CMD ["python", "-m", "ai_sub.main"]
