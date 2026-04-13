"""
SQLite database layer for ViralClipper.
Handles all persistence: videos, clips, feedback, and learning profile.
"""

import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    channel TEXT,
    duration REAL,
    language TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    video_id TEXT REFERENCES videos(id),
    title TEXT,
    start_time REAL,
    end_time REAL,
    duration REAL,
    viral_score REAL,
    category TEXT,
    hook TEXT,
    reasoning TEXT,
    suggested_caption TEXT,
    file_path TEXT,
    thumbnail_path TEXT,
    subtitle_style TEXT DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id TEXT REFERENCES clips(id),
    performance_rating INTEGER,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    retention_rate REAL,
    best_moment TEXT,
    notes TEXT,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_profile (
    id INTEGER PRIMARY KEY,
    profile_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clips_video_id ON clips(video_id);
CREATE INDEX IF NOT EXISTS idx_feedback_clip_id ON feedback(clip_id);
"""


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database schema."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    logger.info(f"Database initialized at {DB_PATH}")


# ─── Video Operations ─────────────────────────────────────────────────────────

def upsert_video(
    video_id: str,
    url: str,
    title: str,
    channel: str,
    duration: float,
    language: str,
    metadata: dict,
) -> None:
    """Insert or update a video record."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO videos (id, url, title, channel, duration, language, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                channel = excluded.channel,
                duration = excluded.duration,
                language = excluded.language,
                metadata = excluded.metadata,
                processed_at = CURRENT_TIMESTAMP
            """,
            (video_id, url, title, channel, duration, language, json.dumps(metadata)),
        )
    logger.debug(f"Upserted video {video_id}")


def get_video(video_id: str) -> Optional[dict]:
    """Fetch a video record by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        if row:
            result = dict(row)
            if result.get("metadata"):
                result["metadata"] = json.loads(result["metadata"])
            return result
    return None


def list_videos(limit: int = 100, offset: int = 0) -> list[dict]:
    """List all processed videos, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY processed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item.get("metadata"):
                item["metadata"] = json.loads(item["metadata"])
            result.append(item)
        return result


# ─── Clip Operations ──────────────────────────────────────────────────────────

def insert_clip(clip: dict) -> None:
    """Insert a clip record."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO clips
            (id, video_id, title, start_time, end_time, duration, viral_score,
             category, hook, reasoning, suggested_caption, file_path, thumbnail_path, subtitle_style)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clip["id"],
                clip["video_id"],
                clip.get("title"),
                clip.get("start_time"),
                clip.get("end_time"),
                clip.get("duration"),
                clip.get("viral_score"),
                clip.get("category"),
                clip.get("hook"),
                clip.get("reasoning"),
                clip.get("suggested_caption"),
                clip.get("file_path"),
                clip.get("thumbnail_path"),
                clip.get("subtitle_style", "default"),
            ),
        )
    logger.debug(f"Inserted clip {clip['id']}")


def update_clip_paths(clip_id: str, file_path: str, thumbnail_path: str) -> None:
    """Update the file paths for a rendered clip."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE clips SET file_path = ?, thumbnail_path = ? WHERE id = ?",
            (file_path, thumbnail_path, clip_id),
        )


def get_clip(clip_id: str) -> Optional[dict]:
    """Fetch a clip by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return dict(row) if row else None


def list_clips(video_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    """List clips, optionally filtered by video ID."""
    with get_connection() as conn:
        if video_id:
            rows = conn.execute(
                "SELECT * FROM clips WHERE video_id = ? ORDER BY viral_score DESC LIMIT ?",
                (video_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM clips ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def list_clips_without_feedback() -> list[dict]:
    """Return clips that have not yet received user feedback."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.* FROM clips c
            LEFT JOIN feedback f ON f.clip_id = c.id
            WHERE f.id IS NULL AND c.file_path IS NOT NULL
            ORDER BY c.created_at DESC
            """,
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Feedback Operations ──────────────────────────────────────────────────────

def insert_feedback(feedback: dict) -> int:
    """Insert user feedback for a clip. Returns the inserted row ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback
            (clip_id, performance_rating, views, likes, comments,
             retention_rate, best_moment, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback["clip_id"],
                feedback.get("performance_rating"),
                feedback.get("views"),
                feedback.get("likes"),
                feedback.get("comments"),
                feedback.get("retention_rate"),
                feedback.get("best_moment"),
                feedback.get("notes"),
            ),
        )
        return cursor.lastrowid


def get_feedback_for_clip(clip_id: str) -> Optional[dict]:
    """Return the most recent feedback for a clip."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM feedback WHERE clip_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (clip_id,),
        ).fetchone()
        return dict(row) if row else None


def get_all_feedback_with_clips() -> list[dict]:
    """Join feedback with clip data for learning analysis."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT f.*, c.category, c.duration, c.viral_score, c.hook,
                   c.start_time, c.end_time, c.video_id,
                   v.channel
            FROM feedback f
            JOIN clips c ON c.id = f.clip_id
            JOIN videos v ON v.id = c.video_id
            ORDER BY f.submitted_at DESC
            """,
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Learning Profile ─────────────────────────────────────────────────────────

def save_learning_profile(profile: dict) -> None:
    """Upsert the singleton learning profile."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO learning_profile (id, profile_data, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                profile_data = excluded.profile_data,
                updated_at = CURRENT_TIMESTAMP
            """,
            (json.dumps(profile),),
        )


def get_learning_profile() -> Optional[dict]:
    """Load the learning profile, or None if none exists."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM learning_profile WHERE id = 1"
        ).fetchone()
        if row:
            data = dict(row)
            data["profile_data"] = json.loads(data["profile_data"])
            return data
    return None


# ─── Stats ────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return aggregate statistics for the dashboard."""
    with get_connection() as conn:
        total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        total_clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        total_feedback = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        avg_score_row = conn.execute(
            "SELECT AVG(viral_score) FROM clips WHERE viral_score IS NOT NULL"
        ).fetchone()
        avg_score = round(avg_score_row[0], 2) if avg_score_row[0] else 0.0

        pending_feedback = conn.execute(
            """
            SELECT COUNT(*) FROM clips c
            LEFT JOIN feedback f ON f.clip_id = c.id
            WHERE f.id IS NULL AND c.file_path IS NOT NULL
            """
        ).fetchone()[0]

        top_clips = conn.execute(
            """
            SELECT c.id, c.title, c.viral_score, f.views, f.performance_rating
            FROM clips c
            JOIN feedback f ON f.clip_id = c.id
            ORDER BY f.views DESC
            LIMIT 5
            """
        ).fetchall()

    return {
        "total_videos": total_videos,
        "total_clips": total_clips,
        "total_feedback": total_feedback,
        "avg_viral_score": avg_score,
        "pending_feedback": pending_feedback,
        "top_clips": [dict(r) for r in top_clips],
    }
