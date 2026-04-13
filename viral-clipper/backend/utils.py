"""
Shared utility helpers for ViralClipper.
"""

import io
import logging
import re
import sys
import unicodedata
from pathlib import Path

# ─── Windows UTF-8 fix ───────────────────────────────────────────────────────
# The Windows console uses cp1252 by default which can't encode many unicode
# characters (arrows, emoji, etc.) used in log messages.
# Force UTF-8 on stdout/stderr at import time.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except AttributeError:
        # Fallback for older Python versions
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ─── Logging Setup ────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure structured logging to console and optionally to file."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    console_handler = logging.StreamHandler(sys.stdout)
    # Use errors="replace" so any remaining unencodable chars become "?"
    if hasattr(console_handler.stream, "reconfigure"):
        try:
            console_handler.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    handlers: list[logging.Handler] = [console_handler]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(str(log_file), encoding="utf-8")
        )

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )


# ─── String Helpers ───────────────────────────────────────────────────────────

def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a safe filename slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:max_length].rstrip("-")


def format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for ffmpeg/ASS use."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def ass_timestamp(seconds: float) -> str:
    """Format seconds as H:MM:SS.cc for ASS subtitle format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


# ─── File Helpers ─────────────────────────────────────────────────────────────

def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist, return path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_size_mb(path: Path) -> float:
    """Return file size in megabytes."""
    return path.stat().st_size / (1024 * 1024)


# ─── Video Validation ─────────────────────────────────────────────────────────

def validate_youtube_url(url: str) -> bool:
    """Return True if the URL looks like a valid YouTube URL."""
    patterns = [
        r"^https?://(www\.)?youtube\.com/watch\?v=[\w-]+",
        r"^https?://youtu\.be/[\w-]+",
        r"^https?://(www\.)?youtube\.com/shorts/[\w-]+",
        r"^https?://(www\.)?youtube\.com/live/[\w-]+",
    ]
    return any(re.match(p, url.strip()) for p in patterns)


def extract_video_id(url: str) -> str | None:
    """Extract the YouTube video ID from a URL."""
    patterns = [
        r"[?&]v=([\w-]{11})",
        r"youtu\.be/([\w-]{11})",
        r"shorts/([\w-]{11})",
        r"live/([\w-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
