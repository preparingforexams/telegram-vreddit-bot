import logging
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

_LOG = logging.getLogger(__name__)
ReadinessProbe = Callable[[], bool]


class _RequestHandler(BaseHTTPRequestHandler):
    check_readiness: ReadinessProbe = lambda: True  # noqa: E731

    # noinspection PyPep8Naming
    def do_GET(self):
        if self.check_readiness():
            self.send_response(200)
        else:
            self.send_response(503)


class ReadinessServer:
    def __init__(self, port: int = 8080):
        self._server = HTTPServer(("localhost", port), _RequestHandler)
        self._thread = Thread(target=self._run, daemon=True, name="ReadinessServer")

    def start(self, check_readiness: ReadinessProbe):
        if self._thread.is_alive():
            raise ValueError("Already started")

        # Yeah, this won't work for multiple instances, but I'm okay with that.
        _RequestHandler.check_readiness = check_readiness
        self._thread.start()

    def _run(self):
        try:
            self._server.serve_forever()
        except BaseException as e:
            _LOG.error("Server stopped unexpectedly", exc_info=e)
