import asyncio
import logging

import click
import sentry_sdk
import uvloop
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


@app.command
@click.pass_obj
def handle_updates(config: Config):
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    command.handle_updates.run(config)


@app.command
@click.pass_obj
def download(config: Config):
    uvloop.run(command.download.run(config))


@app.command
@click.pass_obj
def telegram_audio_convert(config: Config):
    uvloop.run(command.telegram_audio_convert.run(config))


@app.command
@click.pass_obj
def url_alias_resolution(config: Config):
    uvloop.run(command.url_alias_resolution.run(config))


@app.command
@click.pass_obj
def youtube_url_convert(config: Config):
    uvloop.run(command.youtube_url_convert.run(config))


if __name__ == "__main__":
    app.main()
