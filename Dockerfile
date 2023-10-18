FROM python:3.12-slim-bookworm AS base

RUN groupadd --system --gid 500 app
RUN useradd --system --uid 500 --gid app --create-home --home-dir /app -s /bin/bash app

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends \
      curl \
      ffmpeg  \
      tini  \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists /var/cache/apt/archives

# renovate: datasource=pypi depName=poetry
ENV POETRY_VERSION=1.6.1
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
ENV PATH="$POETRY_HOME/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python3 -

USER app
WORKDIR /app

FROM base AS prod

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]

RUN poetry install --no-interaction --ansi --only=main --no-root

COPY src/cancer ./src/cancer

RUN poetry install --no-interaction --ansi --only-root

ARG build
ENV BUILD_SHA=$build

ENTRYPOINT [ "tini", "--", "poetry", "run", "python", "-m", "cancer" ]
