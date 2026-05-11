from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .api import handle_request
from .config import load_local_env
from .email_resume_ingest.scheduler import EmailResumeIngestScheduler


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
    scheduler: EmailResumeIngestScheduler | None = None
    if str(os.getenv("SCREENING_EMAIL_INGEST_SCHEDULER_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        poll_seconds = max(5, int(os.getenv("SCREENING_EMAIL_INGEST_SCHEDULER_POLL_SECONDS", "60") or 60))
        scheduler = EmailResumeIngestScheduler()
        scheduler.start_in_background(poll_seconds=poll_seconds)
        print(f"[email-ingest] scheduler started, poll_seconds={poll_seconds}")
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Listening on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        if scheduler is not None:
            scheduler.stop()


if __name__ == "__main__":
    run()
