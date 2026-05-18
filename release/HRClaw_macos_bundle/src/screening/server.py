from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .api import handle_request
from .config import load_local_env


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "ScreeningMVP/0.1"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        result = handle_request(self)
        if len(result) == 2:
            status, body = result
            content_type = "application/json; charset=utf-8"
            extra_headers = {}
        elif len(result) == 3:
            status, body, content_type = result
            extra_headers = {}
        else:
            status, body, content_type, extra_headers = result
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for key, value in extra_headers.items():
            self.send_header(str(key), str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    load_local_env()
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
