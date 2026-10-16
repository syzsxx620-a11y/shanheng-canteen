import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4

class Repository:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS meals (id TEXT PRIMARY KEY, created TEXT, canteen TEXT, meal TEXT, mode TEXT, report TEXT)')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, canteen, meal, mode, report):
        with self.connect() as conn:
            conn.execute('INSERT INTO meals VALUES (?, ?, ?, ?, ?, ?)',
                         (str(uuid4()), datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'), canteen, meal, mode, json.dumps(report, ensure_ascii=False)))

    def records(self):
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM meals ORDER BY created DESC').fetchall()
        return [dict(id=r[0], created=r[1], canteen=r[2], meal=r[3], mode=r[4], **json.loads(r[5])) for r in rows]
