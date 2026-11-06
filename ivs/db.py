from __future__ import annotations
import sqlite3, json, datetime as dt
from pathlib import Path

MIGRATIONS = [
# 1: core schema
"""
CREATE TABLE content_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL,
  key TEXT NOT NULL UNIQUE,            -- canonical content key, e.g. quran:94:5-6 / hadith:bukhari:13
  topic TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  review_reason TEXT,
  source_json TEXT,                    -- provenance (editions, hashes, urls, verification date)
  text_fingerprint TEXT,               -- sha256 of normalized source text
  script_text TEXT,                    -- normalized text used for similarity
  title TEXT, description TEXT, tags TEXT,
  video_path TEXT, video_sha256 TEXT, thumbnail_path TEXT,
  scheduled_for TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  published_at TEXT, platform_id TEXT, platform_url TEXT, error TEXT
);
CREATE INDEX idx_items_status ON content_items(status);
CREATE UNIQUE INDEX idx_items_fp ON content_items(text_fingerprint) WHERE text_fingerprint IS NOT NULL;
CREATE UNIQUE INDEX idx_items_vhash ON content_items(video_sha256) WHERE video_sha256 IS NOT NULL;

CREATE TABLE used_ayat(               -- ayah-level overlap detection
  surah INTEGER NOT NULL, ayah INTEGER NOT NULL, item_id INTEGER NOT NULL,
  PRIMARY KEY(surah, ayah)
);
CREATE TABLE rejections(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, key TEXT, category TEXT, reason TEXT NOT NULL
);
CREATE TABLE assets_used(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, name TEXT, kind TEXT,
  source_url TEXT, license TEXT, attribution TEXT
);
CREATE TABLE publish_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, platform TEXT NOT NULL,
  ts TEXT NOT NULL, ok INTEGER NOT NULL, platform_id TEXT, url TEXT, detail TEXT
);
CREATE TABLE quota_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, ts TEXT NOT NULL, units INTEGER NOT NULL, note TEXT
);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE event_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, level TEXT NOT NULL, item_id INTEGER, msg TEXT NOT NULL
);
""",
# 2: verification statuses, scoring, authenticity audit trail, anti-repetition log
"""
ALTER TABLE content_items ADD COLUMN religious_verification TEXT;   -- VERIFIED | NEEDS_HUMAN_REVIEW | REJECTED
ALTER TABLE content_items ADD COLUMN content_quality TEXT;          -- APPROVED | NEEDS_REVISION | REJECTED
ALTER TABLE content_items ADD COLUMN engagement_score INTEGER;
ALTER TABLE content_items ADD COLUMN hook_candidates TEXT;
ALTER TABLE content_items ADD COLUMN title_candidates TEXT;
CREATE TABLE claims(
  id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id TEXT NOT NULL UNIQUE, item_id INTEGER NOT NULL, kind TEXT NOT NULL,
  arabic TEXT, translation TEXT, translator TEXT, source_title TEXT, reference TEXT, grade TEXT, method TEXT,
  source_url TEXT, license TEXT, verified_on TEXT, reviewer_status TEXT NOT NULL
);
CREATE TABLE style_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, pattern TEXT, item_id INTEGER
);
CREATE INDEX idx_style_kind ON style_log(kind);
""",
# 3: 3D direction, storyboards and anti-repetition memory
"""
CREATE TABLE direction_log(id INTEGER PRIMARY KEY AUTOINCREMENT, story_id TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL, ts TEXT NOT NULL);
CREATE INDEX idx_direction_kind ON direction_log(kind, id);
CREATE TABLE storyboards(story_id TEXT PRIMARY KEY, concept_json TEXT NOT NULL, storyboard_json TEXT NOT NULL, characters_json TEXT NOT NULL, qc_json TEXT, created_at TEXT NOT NULL);
""",
# 4: director's treatments, procedural asset catalog, scene manifest (regenerate shots independently)
"""
CREATE TABLE treatments(story_id TEXT PRIMARY KEY, style_id TEXT NOT NULL, treatment_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE assets(asset_id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT, params_json TEXT, path TEXT, license TEXT NOT NULL, provenance TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE scene_manifest(story_id TEXT NOT NULL, scene_no INTEGER NOT NULL, shot_key TEXT, technique TEXT, env TEXT, camera TEXT, spec_json TEXT, status TEXT NOT NULL, path TEXT, updated_at TEXT NOT NULL, PRIMARY KEY(story_id, scene_no));
""",
]

STATUSES = {"queued", "verified", "generating", "rendered", "needs_review",
            "approved", "published", "failed", "skipped"}

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

class DB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        cur = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for i, sql in enumerate(MIGRATIONS[cur:], start=cur + 1):
            self.conn.executescript(sql)
            self.conn.execute(f"PRAGMA user_version={i}")
        self.conn.commit()

    # ---- helpers
    def log(self, level: str, msg: str, item_id: int | None = None) -> None:
        self.conn.execute("INSERT INTO event_log(ts,level,item_id,msg) VALUES(?,?,?,?)", (now(), level, item_id, msg))
        self.conn.commit()

    def reject(self, key: str | None, category: str | None, reason: str) -> None:
        self.conn.execute("INSERT INTO rejections(ts,key,category,reason) VALUES(?,?,?,?)", (now(), key, category, reason))
        self.conn.commit()

    def set_status(self, item_id: int, status: str, **fields) -> None:
        assert status in STATUSES, status
        fields["status"] = status
        fields["updated_at"] = now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE content_items SET {cols} WHERE id=?", (*fields.values(), item_id))
        self.conn.commit()

    def get_item(self, item_id: int):
        return self.conn.execute("SELECT * FROM content_items WHERE id=?", (item_id,)).fetchone()

    def items(self, status: str | None = None):
        if status:
            return self.conn.execute("SELECT * FROM content_items WHERE status=? ORDER BY id", (status,)).fetchall()
        return self.conn.execute("SELECT * FROM content_items ORDER BY id").fetchall()

    def setting(self, key: str, default: str | None = None) -> str | None:
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def put_setting(self, key: str, value: str) -> None:
        self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()
