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
        release=os.getenv("BUILD_SHA") or "dirty",
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0,
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


@app.command("youtube_url_convert")
def youtube_url_convert():
    command.youtube_url_convert.run()


if __name__ == "__main__":
    _setup_logging()
    _setup_sentry()

    app.main()
