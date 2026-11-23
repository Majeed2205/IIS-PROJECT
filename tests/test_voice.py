import json
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from assistant import turnlog
from assistant.chat import GIVE_UP, GREETING
from assistant.understand import understand
from assistant.voice import PAGE, VoiceCall, make_server

READ_BACK = "So that's a haircut on Friday at 5:30 pm. Is that right?"


class VoiceCallTests(unittest.TestCase):
    def test_a_call_is_answered_like_a_typed_one(self):
        call = VoiceCall("summarise", understand)
        self.assertEqual(call.start(), {"reply": GREETING, "finished": False})
        self.assertEqual(call.turn("A haircut on Friday at half five"), {"reply": READ_BACK, "finished": False})
        self.assertEqual(call.turn("Yes")["reply"], "Booked: haircut on Friday at 5:30 pm.")

    def test_a_new_call_starts_afresh(self):
        call = VoiceCall("clarify", understand)
        call.start()
        call.turn("A haircut on Friday at half five")  # booked
        call.start()
        self.assertEqual(call.turn("A haircut on Friday at half five")["reply"], "Booked: haircut on Friday at 5:30 pm.")

    def test_a_handover_ends_the_call(self):
        call = VoiceCall("clarify", understand)
        call.start()
        answers = [call.turn("I'm busy") for _ in range(3)]
        self.assertEqual(answers[2], {"reply": GIVE_UP, "finished": True})

    def test_the_planted_error_switch_works_by_voice(self):
        call = VoiceCall("summarise", understand, mishear=True)
        call.start()
        self.assertEqual(call.turn("A haircut on Friday at half five")["reply"],
                         "So that's a haircut on Friday at 6:15 pm. Is that right?")

    def test_each_call_gets_its_own_log_only_with_the_switch(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        logs = Path(folder.name) / "logs"
        with mock.patch.object(turnlog, "LOG_DIR", logs):
            call = VoiceCall("summarise", understand)
            call.start()
            call.turn("A haircut on Friday at half five")
            self.assertFalse(logs.exists())
            call = VoiceCall("summarise", understand, logging=True)
            for _ in range(2):
                call.start()
                call.turn("A haircut on Friday at half five")
        files = sorted(logs.glob("*.jsonl"))
        self.assertEqual(len(files), 2)
        self.assertEqual([len(f.read_text().splitlines()) for f in files], [1, 1])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(VoiceCall("summarise", understand), port=0)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def send(self, path, body=None, kind="application/json", host=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        request = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")
        if data is not None:
            request.add_header("Content-Type", kind)
        if host:
            request.add_header("Host", host)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, ""

    def test_the_page(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")  # only this computer can open it
        status, page = self.send("/")
        self.assertEqual(status, 200)
        self.assertEqual(page, PAGE.read_text(encoding="utf-8"))
        self.assertIn('id="talk"', page)
        self.assertIn('id="transcript" hidden', page)  # hidden like a phone call, unless switched on

    def test_a_call_over_the_page(self):
        self.assertEqual(json.loads(self.send("/start", {})[1])["reply"], GREETING)
        status, body = self.send("/turn", {"text": "A haircut on Friday at half five"})
        self.assertEqual((status, json.loads(body)), (200, {"reply": READ_BACK, "finished": False}))

    def test_requests_it_refuses(self):
        self.assertEqual(self.send("/nothing")[0], 404)
        self.assertEqual(self.send("/turn", b"not json")[0], 400)
        self.assertEqual(self.send("/turn", b"text=hi", kind="text/plain")[0], 415)  # a form on another site
        self.assertEqual(self.send("/turn", {"text": "hi"}, host="evil.example")[0], 403)
        self.assertEqual(self.send("/turn", {"text": 5})[0], 400)
        self.assertEqual(self.send("/turn", b"[" * 5000 + b"]" * 5000)[0], 400)  # nested too deeply
        self.assertEqual(self.send("/turn", {"text": "x" * 20000})[0], 400)  # far too long for one turn
        self.assertEqual(self.send("/turn", {"text": "   "})[0], 400)  # silence is never a turn
        status, body = self.send("/turn", {"text": "Friday"}, kind="application/json; charset=utf-8")
        self.assertEqual(status, 200)  # what some browsers send

    def test_the_address_in_the_readme_works(self):
        self.assertEqual(self.send("/turn", {"text": "hi"}, host=f"localhost:{self.port}")[0], 200)

    def raw(self, head):
        line = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(line.close)
        line.sendall(head.encode())
        return line.recv(100).split(b"\r\n")[0]

    def test_a_wrong_length_is_refused_at_once(self):
        for length in ["-1", "abc"]:
            head = (f"POST /turn HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {length}\r\n\r\n")
            self.assertIn(b"400", self.raw(head))

    def test_a_quiet_connection_does_not_hold_up_the_call(self):
        quiet = socket.create_connection(("127.0.0.1", self.port))  # like a spare one a browser opens
        self.addCleanup(quiet.close)
        self.assertEqual(self.send("/start", {})[0], 200)


if __name__ == "__main__":
    unittest.main()
