# syntax=docker/dockerfile:1.7
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV SAA_SQL_MIGRATION_SEARCH=sql/migrations:*.sql,.:upgrade_*.sql

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        git \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=secret,id=GITHUB_TOKEN \
    if [ -f /run/secrets/GITHUB_TOKEN ]; then \
        git config --global url."https://x-access-token:$(cat /run/secrets/GITHUB_TOKEN)@github.com/".insteadOf "ssh://git@github.com/"; \
    fi \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn \
    && if [ -f /run/secrets/GITHUB_TOKEN ]; then \
        git config --global --unset-all url."https://x-access-token:$(cat /run/secrets/GITHUB_TOKEN)@github.com/".insteadOf; \
    fi

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

COPY entrypoint.py .
ENTRYPOINT ["python", "entrypoint.py"]
