import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from idea_check.checker import build_messages, check_idea, parse_reply
from idea_check.server import make_handler
from idea_check.store import Store

ANSWERS = {
    "idea": "A script that renames my camera photos by date",
    "who": "Me",
    "today": "I rename them by hand",
    "cost": "About 20 minutes a week",
}

GOOD_REPLY = json.dumps({
    "verdict": "Build",
    "why": "You have the problem and it's quick to solve.",
    "missing_facts": "None; you are the user.",
    "question_to_send": "n/a",
    "done_means": "Running the script renames every photo in a folder to its capture date.",
    "first_version": "A script that prints the new name for each photo without renaming.",
})


class FakeModel:
    def __init__(self, reply=GOOD_REPLY):
        self.reply = reply
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class CheckerTests(unittest.TestCase):
    def test_prompt_includes_all_three_answers(self):
        user = build_messages(ANSWERS)[1]["content"]
        for value in ANSWERS.values():
            self.assertIn(value, user)

    def test_parses_json_wrapped_in_text(self):
        result = parse_reply("Sure! ```json\n" + GOOD_REPLY + "\n```")
        self.assertEqual(result["verdict"], "Build")

    def test_rejects_unknown_verdict(self):
        bad = json.loads(GOOD_REPLY) | {"verdict": "Maybe"}
        with self.assertRaises(ValueError):
            parse_reply(json.dumps(bad))

    def test_rejects_missing_field(self):
        bad = json.loads(GOOD_REPLY)
        del bad["done_means"]
        with self.assertRaises(ValueError):
            parse_reply(json.dumps(bad))

    def test_rejects_non_json(self):
        with self.assertRaises(ValueError):
            parse_reply("I think you should build it.")

    def test_check_idea_uses_model(self):
        model = FakeModel()
        self.assertEqual(check_idea(ANSWERS, model)["verdict"], "Build")
        self.assertEqual(len(model.calls), 1)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model = FakeModel()
        store = Store(str(Path(self.tmp.name) / "ideas.db"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, self.model))
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def test_serves_page(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Idea Check", body)

    def test_check_saves_and_lists_idea(self):
        status, body = self.request("/api/ideas", ANSWERS)
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["result"]["verdict"], "Build")

        status, body = self.request("/api/ideas")
        items = json.loads(body)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["idea"], ANSWERS["idea"])

    def test_empty_answer_is_rejected(self):
        status, body = self.request("/api/ideas", ANSWERS | {"cost": "  "})
        self.assertEqual(status, 400)
        self.assertIn("cost", json.loads(body)["error"])
        self.assertEqual(self.model.calls, [])

    def test_model_failure_is_reported_and_not_saved(self):
        self.model.reply = ConnectionError("model is down")
        status, body = self.request("/api/ideas", ANSWERS)
        self.assertEqual(status, 502)
        self.assertIn("model is down", json.loads(body)["error"])
        _, body = self.request("/api/ideas")
        self.assertEqual(json.loads(body), [])


if __name__ == "__main__":
    unittest.main()
