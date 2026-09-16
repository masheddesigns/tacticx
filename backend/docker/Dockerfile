FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /code/pyproject.toml
RUN pip install --no-cache-dir -e ".[dev]"

COPY . /code

EXPOSE 8000
