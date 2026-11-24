"""Voice in the browser (step 7): a simulated phone line.

Status: simulated. A small web server on this computer shows one page. The browser's own
speech recognition turns what the caller says into text, the same Conversation as in the
terminal answers it, and the browser reads the reply aloud with one of the computer's voices.

Run:  python3 -m assistant.voice summarise      then open http://localhost:8000 in Chrome or Safari.
It takes the same --mishear and --log switches as the terminal chat. Only this computer can
open the page. Chrome sends the caller's audio to Google to recognise it, so use made-up details.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .chat import GREETING, Conversation, read_args, setup_lines
from .model import ModelReader
from .policy import STRATEGIES
from .slots import Calendar
from .turnlog import TurnFile, new_log_path

PAGE = Path(__file__).with_name("voice.html")
PORT = 8000
MOST_BYTES = 10000  # far more than anyone says in one turn


class VoiceCall:
    """The call on the simulated phone line. Each new call starts with a fresh calendar."""

    def __init__(self, strategy: str, reader, mishear: bool = False, logging: bool = False):
        self.strategy = strategy
        self.reader = reader
        self.mishear = mishear
        self.logging = logging
        self.chat = None

    def start(self) -> dict:
        path = new_log_path(self.strategy)
        log = TurnFile(path) if self.logging else None
        self.chat = Conversation(Calendar.load(), self.strategy, call_id=path.stem, reader=self.reader,
                                 mishear=self.mishear, log=log)
        return {"reply": GREETING, "finished": False}

    def turn(self, text: str) -> dict:
        """One thing the caller said, as the recogniser heard it."""
        if self.chat is None:
            self.start()
        reply = self.chat.reply(text)
        return {"reply": reply, "finished": self.chat.finished}


def make_server(call: VoiceCall, port: int = PORT) -> ThreadingHTTPServer:
    """A server for this computer only (127.0.0.1). Port 0 picks any free port, for the tests.

    Each connection gets its own thread, so a connection that sends nothing (browsers open spare
    ones) cannot hold up the others. The lock lets the call answer one request at a time.
    """
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                return self.send_error(404)
            self.answer(200, "text/html; charset=utf-8", PAGE.read_bytes())

        def do_POST(self):
            # Another website open in the browser must not be able to talk to the assistant:
            # it would be sent with another Host, or as a form instead of JSON.
            own = [f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"]
            if self.headers.get("Host") not in own:
                return self.send_error(403)
            if self.headers.get_content_type() != "application/json":  # "; charset=utf-8" is fine
                return self.send_error(415)
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or int(length) > MOST_BYTES:
                return self.send_error(400)
            try:
                body = json.loads(self.rfile.read(int(length)))
            except (ValueError, RecursionError):  # not JSON, or nested too deeply to read
                return self.send_error(400)
            with lock:
                if self.path == "/start":
                    said = call.start()
                elif self.path == "/turn":
                    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
                        return self.send_error(400)
                    if not body["text"].strip():
                        return self.send_error(400)  # silence is never a turn
                    said = call.turn(body["text"])
                else:
                    return self.send_error(404)
            self.answer(200, "application/json", json.dumps(said).encode())

        def answer(self, status: int, kind: str, data: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass  # keep the terminal quiet; the turn log records the calls

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    strategy, mishear, logging = read_args(sys.argv[1:])
    if strategy not in STRATEGIES:
        print("Usage: python3 -m assistant.voice [repeat | clarify | summarise] [--mishear] [--log]")
        return
    reader = ModelReader()
    try:
        server = make_server(VoiceCall(strategy, reader, mishear, logging))
    except OSError:
        print(f"Port {PORT} is already in use. Stop the other voice line (Ctrl+C), then try again.")
        return
    print(f"Demo Salon voice line ({strategy}, simulated).")
    for line in setup_lines(reader, mishear):
        print(line)
    if logging:
        print("Turn log: on. Each call is written to its own file in logs/, including what the caller says.")
    print(f"Open http://localhost:{PORT} in Chrome or Safari. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
