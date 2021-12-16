FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

COPY requirements.txt .

RUN pip install -r requirements.txt --no-cache

COPY cancer .

ARG build
ENV BUILD_SHA=$build

ENTRYPOINT [ "python", "-m", "cancer" ]
