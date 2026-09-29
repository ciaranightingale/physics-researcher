"""SQLite storage: your posted-videos log, the article-link cache, and snapshots of recently shown story groups."""

import json
import sqlite3
from pathlib import Path

from .models import PostedVideo

_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS videos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    story_title TEXT NOT NULL,
    video_title TEXT NOT NULL,
    format      TEXT NOT NULL CHECK (format IN ('short', 'long')),
    platform    TEXT NOT NULL,
    video_url   TEXT NOT NULL UNIQUE,
    posted_on   TEXT NOT NULL,
    note        TEXT
);
-- Every story link and paper identifier a video is about. A story is "covered" if any of its keys appear here.
CREATE TABLE IF NOT EXISTS video_keys (
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    PRIMARY KEY (video_id, key)
);
CREATE INDEX IF NOT EXISTS video_keys_by_key ON video_keys(key);
CREATE TABLE IF NOT EXISTS link_cache (
    url_key     TEXT PRIMARY KEY,
    identifiers TEXT NOT NULL,
    status      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS story_snapshots (
    group_id TEXT PRIMARY KEY,
    headline TEXT NOT NULL,
    keys     TEXT NOT NULL,
    seen_at  TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        if str(path) != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")

    # --- posted videos ---------------------------------------------------

    def add_video(self, *, story_title: str, video_title: str, format: str, platform: str, video_url: str,
                  posted_on: str, note: str | None, keys: list[str]) -> tuple[PostedVideo, bool]:
        """Logs a video and attaches it to the story keys. Logging the same video URL again just adds keys."""
        with self.db:
            row = self.db.execute("SELECT id FROM videos WHERE video_url = ?", (video_url,)).fetchone()
            existed = row is not None
            if existed:
                video_id = row["id"]
            else:
                cur = self.db.execute(
                    "INSERT INTO videos (story_title, video_title, format, platform, video_url, posted_on, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (story_title, video_title, format, platform, video_url, posted_on, note),
                )
                video_id = cur.lastrowid
            self.db.executemany("INSERT OR IGNORE INTO video_keys (video_id, key) VALUES (?, ?)", [(video_id, k) for k in keys])
        return self.get_video(video_id), existed

    def get_video(self, video_id: int) -> PostedVideo:
        row = self.db.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return _video(row)

    def video_keys(self, video_id: int) -> list[str]:
        return [r["key"] for r in self.db.execute("SELECT key FROM video_keys WHERE video_id = ? ORDER BY key", (video_id,))]

    def delete_video(self, video_id: int) -> bool:
        with self.db:
            return self.db.execute("DELETE FROM videos WHERE id = ?", (video_id,)).rowcount > 0

    def videos_for_keys(self, keys: list[str]) -> list[PostedVideo]:
        if not keys:
            return []
        marks = ",".join("?" * len(keys))
        rows = self.db.execute(
            f"SELECT DISTINCT v.* FROM videos v JOIN video_keys k ON k.video_id = v.id WHERE k.key IN ({marks}) ORDER BY v.posted_on, v.id",
            keys,
        ).fetchall()
        return [_video(r) for r in rows]

    def list_videos(self, since_iso: str | None = None, format: str | None = None) -> list[PostedVideo]:
        sql, args = "SELECT * FROM videos WHERE 1=1", []
        if since_iso:
            sql, args = sql + " AND posted_on >= ?", [*args, since_iso]
        if format:
            sql, args = sql + " AND format = ?", [*args, format]
        return [_video(r) for r in self.db.execute(sql + " ORDER BY posted_on DESC, id DESC", args)]

    # --- article link cache ----------------------------------------------

    def cached_links(self, url_keys: list[str]) -> dict[str, tuple[list[str], str]]:
        if not url_keys:
            return {}
        marks = ",".join("?" * len(url_keys))
        rows = self.db.execute(f"SELECT * FROM link_cache WHERE url_key IN ({marks})", url_keys).fetchall()
        return {r["url_key"]: (json.loads(r["identifiers"]), r["status"]) for r in rows}

    def cache_links(self, url_key: str, identifiers: list[str], status: str, fetched_at: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO link_cache (url_key, identifiers, status, fetched_at) VALUES (?, ?, ?, ?)",
                (url_key, json.dumps(identifiers), status, fetched_at),
            )

    # --- story snapshots (so log_posted_video can take a group_id) --------

    def save_snapshots(self, groups: list[tuple[str, str, list[str]]], seen_at: str) -> None:
        with self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO story_snapshots (group_id, headline, keys, seen_at) VALUES (?, ?, ?, ?)",
                [(gid, headline, json.dumps(keys), seen_at) for gid, headline, keys in groups],
            )

    def snapshot(self, group_id: str) -> tuple[str, list[str]] | None:
        row = self.db.execute("SELECT headline, keys FROM story_snapshots WHERE group_id = ?", (group_id,)).fetchone()
        return (row["headline"], json.loads(row["keys"])) if row else None


def _video(row: sqlite3.Row) -> PostedVideo:
    return PostedVideo(
        video_id=row["id"], video_title=row["video_title"], format=row["format"], platform=row["platform"],
        video_url=row["video_url"], posted_on=row["posted_on"], story_title=row["story_title"], note=row["note"],
    )
