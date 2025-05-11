import asyncio
import logging

import click
import sentry_sdk
from bs_config import Env

from cancer import command
from cancer.config import Config, SentryConfig

_LOG = logging.getLogger(__package__)


def _setup_logging():
    logging.basicConfig()
    logging.root.setLevel(logging.WARNING)
    _LOG.level = logging.DEBUG


def _setup_sentry(config: SentryConfig):
    dsn = config.dsn
    if not dsn:
        _LOG.warning("No Sentry DSN found")
        return

    sentry_sdk.init(
        dsn,
        release=config.release,
    )


@click.group()
@click.pass_context
def app(ctx):
    _setup_logging()

    env = Env.load(include_default_dotenv=True)
    config = Config.from_env(env)

    _setup_sentry(config.sentry)

    ctx.obj = config


@app.command("handle_updates")
@click.pass_obj
def handle_updates(config: Config):
    command.handle_updates.run(config)


@app.command("download")
@click.pass_obj
def download(config: Config):
    asyncio.run(command.download.run(config))


@app.command("telegram_audio_convert")
@click.pass_obj
def telegram_audio_convert(config: Config):
    asyncio.run(command.telegram_audio_convert.run(config))


@app.command("youtube_url_convert")
@click.pass_obj
def youtube_url_convert(config: Config):
    asyncio.run(command.youtube_url_convert.run(config))


if __name__ == "__main__":
    app.main()
