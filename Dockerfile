FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SUBTITLEYC_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-chi-sim \
        tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY subtitleyc ./subtitleyc
COPY static ./static

RUN python -m pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "subtitleyc.main:app", "--host", "0.0.0.0", "--port", "8000"]
