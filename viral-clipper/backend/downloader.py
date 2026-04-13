"""
Video downloader module using yt-dlp.
Downloads video + separate audio from any YouTube URL.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

import yt_dlp

from config import (
    AUDIO_FORMAT,
    DOWNLOADS_DIR,
    MAX_VIDEO_QUALITY,
)
from utils import extract_video_id, validate_youtube_url

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when a download fails for a known reason."""


class DownloadResult:
    """Container for the result of a download operation."""

    def __init__(
        self,
        video_id: str,
        video_path: Path,
        audio_path: Path,
        metadata: dict,
    ) -> None:
        self.video_id = video_id
        self.video_path = video_path
        self.audio_path = audio_path
        self.metadata = metadata
        self.title: str = metadata.get("title", "")
        self.channel: str = metadata.get("uploader", "")
        self.duration: float = float(metadata.get("duration", 0))
        self.thumbnail_url: str = metadata.get("thumbnail", "")
        self.language: str = metadata.get("language") or ""

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "video_path": str(self.video_path),
            "audio_path": str(self.audio_path),
            "title": self.title,
            "channel": self.channel,
            "duration": self.duration,
            "thumbnail_url": self.thumbnail_url,
            "language": self.language,
            "metadata": self.metadata,
        }


def _ydl_opts(output_template: str, audio_only: bool = False) -> dict:
    """Build yt-dlp options dict."""
    base: dict = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if audio_only:
        base.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": AUDIO_FORMAT,
                        "preferredquality": "0",  # lossless for WAV
                    }
                ],
            }
        )
    else:
        base["format"] = (
            f"bestvideo[height<={MAX_VIDEO_QUALITY}][ext=mp4]"
            "+bestaudio[ext=m4a]/"
            f"bestvideo[height<={MAX_VIDEO_QUALITY}]+bestaudio/"
            "best"
        )
        base["merge_output_format"] = "mp4"
    return base


def fetch_metadata(url: str) -> dict:
    """Fetch video metadata without downloading."""
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            _raise_friendly(str(e))
    return info


def download(url: str, force: bool = False) -> DownloadResult:
    """
    Download video + audio from *url*.

    Args:
        url: YouTube video URL.
        force: Re-download even if files already exist.

    Returns:
        DownloadResult with paths and metadata.

    Raises:
        DownloadError: On network errors, private/unavailable videos, bad URLs.
    """
    if not validate_youtube_url(url):
        raise DownloadError(f"Invalid YouTube URL: {url!r}")

    video_id = extract_video_id(url)
    if not video_id:
        raise DownloadError(f"Could not extract video ID from: {url!r}")

    video_path = DOWNLOADS_DIR / f"{video_id}.mp4"
    audio_path = DOWNLOADS_DIR / f"{video_id}.{AUDIO_FORMAT}"
    meta_path = DOWNLOADS_DIR / f"{video_id}_meta.json"

    # ── Cache check ──────────────────────────────────────────────────────────
    if not force and video_path.exists() and audio_path.exists() and meta_path.exists():
        logger.info(f"[{video_id}] Cache hit — skipping download")
        with open(meta_path) as f:
            metadata = json.load(f)
        return DownloadResult(video_id, video_path, audio_path, metadata)

    logger.info(f"[{video_id}] Fetching metadata …")
    metadata = fetch_metadata(url)
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    # ── Download video ────────────────────────────────────────────────────────
    if force or not video_path.exists():
        logger.info(f"[{video_id}] Downloading video (≤{MAX_VIDEO_QUALITY}p) …")
        video_tmpl = str(DOWNLOADS_DIR / f"{video_id}.%(ext)s")
        opts = _ydl_opts(video_tmpl, audio_only=False)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            _raise_friendly(str(e))

        # yt-dlp may produce the exact file or with a different ext
        if not video_path.exists():
            candidates = list(DOWNLOADS_DIR.glob(f"{video_id}.*"))
            mp4_candidates = [p for p in candidates if p.suffix == ".mp4"]
            if mp4_candidates:
                video_path = mp4_candidates[0]
            else:
                raise DownloadError(f"Video file not found after download for {video_id}")
        logger.info(f"[{video_id}] Video saved -> {video_path}")

    # ── Download / extract audio ──────────────────────────────────────────────
    if force or not audio_path.exists():
        logger.info(f"[{video_id}] Extracting audio …")
        audio_tmpl = str(DOWNLOADS_DIR / f"{video_id}.%(ext)s")
        opts = _ydl_opts(audio_tmpl, audio_only=True)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            _raise_friendly(str(e))

        if not audio_path.exists():
            raise DownloadError(f"Audio file not found after extraction for {video_id}")
        logger.info(f"[{video_id}] Audio saved -> {audio_path}")

    return DownloadResult(video_id, video_path, audio_path, metadata)


def _raise_friendly(msg: str) -> None:
    """Convert yt-dlp error messages into user-friendly DownloadErrors."""
    msg_lower = msg.lower()
    if "private video" in msg_lower:
        raise DownloadError("This video is private and cannot be downloaded.")
    if "video unavailable" in msg_lower or "not available" in msg_lower:
        raise DownloadError("This video is unavailable in your region or has been removed.")
    if "sign in" in msg_lower or "age" in msg_lower:
        raise DownloadError("This video requires authentication (age-restricted or members-only).")
    if "network" in msg_lower or "connection" in msg_lower:
        raise DownloadError(f"Network error while downloading: {msg}")
    raise DownloadError(f"Download failed: {msg}")
