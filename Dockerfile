FROM ghcr.io/blindfoldedsurgery/poetry:1.1.1-pipx-3.11-bookworm

USER root
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends \
      ffmpeg  \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists /var/cache/apt/archives
USER app

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]

RUN poetry install --no-interaction --ansi --only=main --no-root

COPY src/cancer ./src/cancer

RUN poetry install --no-interaction --ansi --only-root

ARG APP_VERSION
ENV BUILD_SHA=$APP_VERSION

ENTRYPOINT [ "tini", "--", "poetry", "run", "python", "-m", "cancer" ]
