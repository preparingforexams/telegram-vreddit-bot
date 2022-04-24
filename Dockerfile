FROM python:3.10-slim

WORKDIR /app

RUN ln -s /usr/bin/dpkg-split /usr/sbin/dpkg-split
RUN ln -s /usr/bin/dpkg-deb /usr/sbin/dpkg-deb
RUN ln -s /bin/rm /usr/sbin/rm
RUN ln -s /bin/tar /usr/sbin/tar

RUN apt-get update && apt-get install -y ffmpeg gcc make && apt-get clean

RUN pip install poetry --no-cache
RUN poetry config virtualenvs.create false

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]

RUN poetry install --no-dev

COPY src .

ARG build
ENV BUILD_SHA=$build

ENTRYPOINT [ "python", "-m", "cancer" ]
