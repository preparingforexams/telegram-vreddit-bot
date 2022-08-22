import functools

from requests import Session


def build_session(default_timeout: float | int = 60) -> Session:
    session = Session()
    request_with_default_timeout = functools.partial(
        session.request,
        timeout=default_timeout,
    )
    session.request = request_with_default_timeout  # type: ignore
    return session
