"""Save and list checked ideas in a small SQLite file."""

import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    idea       TEXT NOT NULL,
    who        TEXT NOT NULL,
    today      TEXT NOT NULL,
    cost       TEXT NOT NULL,
    verdict    TEXT NOT NULL,
    result     TEXT NOT NULL
)
"""


class Store:
    def __init__(self, path):
        self.path = path
        with self._conn() as conn:
            conn.execute(SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, answers, result):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO ideas (created_at, idea, who, today, cost, verdict, result)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    now,
                    answers["idea"],
                    answers["who"],
                    answers["today"],
                    answers["cost"],
                    result["verdict"],
                    json.dumps(result),
                ),
            )
            return self.get(cur.lastrowid, conn)

    def get(self, idea_id, conn=None):
        conn = conn or self._conn()
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def list(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ideas ORDER BY id DESC").fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row):
    item = dict(row)
    item["result"] = json.loads(item["result"])
    return item
