FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV SAA_SQL_MIGRATION_SEARCH=sql/migrations:*.sql,.:upgrade_*.sql

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY third_party/ucenter-python ./third_party/ucenter-python
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

COPY entrypoint.py .
ENTRYPOINT ["python", "entrypoint.py"]
