FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt --no-cache

COPY vredditbot.py .

ARG build
ENV BUILD_SHA=$build

CMD [ "python", "-m", "vredditbot" ]
