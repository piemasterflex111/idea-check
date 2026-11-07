"""A tiny web server: one page, plus a JSON API to check and list ideas.

Run:  python -m idea_check.server
"""

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .checker import OpenAICompatibleModel, check_idea
from .store import Store

PAGE = (Path(__file__).parent / "static" / "index.html").read_bytes()
REQUIRED = ("idea", "who", "today", "cost")


def make_handler(store, model):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self._send(HTTPStatus.OK, PAGE, "text/html; charset=utf-8")
            elif self.path == "/api/ideas":
                self._json(HTTPStatus.OK, store.list())
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/api/ideas":
                return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                answers = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "Send JSON."})
            answers = {k: str(answers.get(k, "")).strip() for k in REQUIRED}
            empty = [k for k in REQUIRED if not answers[k]]
            if empty:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": f"Fill in: {', '.join(empty)}"})
            try:
                result = check_idea(answers, model)
            except Exception as exc:  # model down or bad reply: tell the user plainly
                return self._json(HTTPStatus.BAD_GATEWAY, {"error": f"AI check failed: {exc}"})
            self._json(HTTPStatus.CREATED, store.add(answers, result))

        def _json(self, status, data):
            self._send(status, json.dumps(data).encode(), "application/json")

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Run the Idea Check web app.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--db", default="ideas.db", help="SQLite file to save ideas in")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(Store(args.db), OpenAICompatibleModel()))
    print(f"Idea Check running on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
