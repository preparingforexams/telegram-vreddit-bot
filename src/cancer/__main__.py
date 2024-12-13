import logging
import os

import click
import sentry_sdk

from cancer import command

_LOG = logging.getLogger("cancer")


def _setup_logging():
    logging.basicConfig()
    _LOG.level = logging.DEBUG


def _setup_sentry():
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        _LOG.warning("No Sentry DSN found")
        return

    sentry_sdk.init(
        dsn,
        release=os.getenv("APP_VERSION") or "dirty",
    )


@click.group()
def app():
    pass


@app.command("handle_updates")
def handle_updates():
    command.handle_updates.run()


@app.command("download")
def download():
    command.download.run()


@app.command("telegram_audio_convert")
def telegram_audio_convert():
    command.telegram_audio_convert.run()


@app.command("youtube_url_convert")
def youtube_url_convert():
    command.youtube_url_convert.run()


if __name__ == "__main__":
    _setup_logging()
    _setup_sentry()

    app.main()
