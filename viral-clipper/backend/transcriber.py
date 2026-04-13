"""
Audio transcription module using openai-whisper.
Generates word-level timestamps for precise subtitle sync.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from config import TRANSCRIPTS_DIR, WHISPER_MODEL

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when transcription fails."""


class TranscriptSegment:
    """A single transcript segment with word-level detail."""

    def __init__(self, start: float, end: float, text: str, words: list[dict]) -> None:
        self.start = start
        self.end = end
        self.text = text.strip()
        self.words = words  # list of {"word": str, "start": float, "end": float}

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "words": self.words,
        }


class TranscriptResult:
    """Complete transcription result for a video."""

    def __init__(
        self,
        video_id: str,
        language: str,
        segments: list[TranscriptSegment],
    ) -> None:
        self.video_id = video_id
        self.language = language
        self.segments = segments

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.segments)

    @property
    def all_words(self) -> list[dict]:
        """Flat list of all words with timestamps."""
        words = []
        for seg in self.segments:
            words.extend(seg.words)
        return words

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "language": self.language,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptResult":
        segments = [
            TranscriptSegment(
                start=s["start"],
                end=s["end"],
                text=s["text"],
                words=s.get("words", []),
            )
            for s in data["segments"]
        ]
        return cls(
            video_id=data["video_id"],
            language=data.get("language", ""),
            segments=segments,
        )


def _transcript_path(video_id: str) -> Path:
    return TRANSCRIPTS_DIR / f"{video_id}_transcript.json"


def _extract_words_from_segment(segment: dict) -> list[dict]:
    """
    Extract word-level timestamps from a Whisper segment.
    Uses the 'words' key if available (requires word_timestamps=True).
    Falls back to splitting the segment equally if words are unavailable.
    """
    if "words" in segment and segment["words"]:
        return [
            {
                "word": w.get("word", "").strip(),
                "start": round(w.get("start", segment["start"]), 3),
                "end": round(w.get("end", segment["end"]), 3),
            }
            for w in segment["words"]
            if w.get("word", "").strip()
        ]

    # Fallback: distribute evenly
    words_text = segment["text"].strip().split()
    if not words_text:
        return []
    duration = (segment["end"] - segment["start"]) / len(words_text)
    result = []
    for i, word in enumerate(words_text):
        result.append(
            {
                "word": word,
                "start": round(segment["start"] + i * duration, 3),
                "end": round(segment["start"] + (i + 1) * duration, 3),
            }
        )
    return result


def transcribe(audio_path: Path, video_id: str, force: bool = False) -> TranscriptResult:
    """
    Transcribe *audio_path* using Whisper and return a TranscriptResult.

    Args:
        audio_path: Path to WAV/MP3 audio file.
        video_id:   YouTube video ID (used for caching).
        force:      Re-transcribe even if cached transcript exists.

    Returns:
        TranscriptResult with word-level timestamps.

    Raises:
        TranscriptionError: On any failure.
    """
    cache_path = _transcript_path(video_id)

    # ── Cache check ───────────────────────────────────────────────────────────
    if not force and cache_path.exists():
        logger.info(f"[{video_id}] Transcript cache hit — loading from disk")
        with open(cache_path) as f:
            data = json.load(f)
        return TranscriptResult.from_dict(data)

    if not audio_path.exists():
        raise TranscriptionError(f"Audio file not found: {audio_path}")

    # ── Lazy-import Whisper ───────────────────────────────────────────────────
    try:
        import whisper
    except ImportError:
        raise TranscriptionError(
            "openai-whisper is not installed. Run: pip install openai-whisper"
        )

    logger.info(f"[{video_id}] Loading Whisper model '{WHISPER_MODEL}' …")
    try:
        model = whisper.load_model(WHISPER_MODEL)
    except Exception as e:
        raise TranscriptionError(f"Failed to load Whisper model: {e}") from e

    logger.info(f"[{video_id}] Transcribing audio (this may take several minutes) …")
    try:
        result = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            verbose=False,
        )
    except Exception as e:
        raise TranscriptionError(f"Transcription failed: {e}") from e

    language: str = result.get("language", "")
    logger.info(f"[{video_id}] Detected language: {language!r}")

    segments: list[TranscriptSegment] = []
    for seg in result.get("segments", []):
        words = _extract_words_from_segment(seg)
        segments.append(
            TranscriptSegment(
                start=round(seg["start"], 3),
                end=round(seg["end"], 3),
                text=seg["text"].strip(),
                words=words,
            )
        )

    transcript = TranscriptResult(
        video_id=video_id,
        language=language,
        segments=segments,
    )

    # ── Save to cache ─────────────────────────────────────────────────────────
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(transcript.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info(
        f"[{video_id}] Transcript saved → {cache_path} "
        f"({len(segments)} segments, {len(transcript.all_words)} words)"
    )

    return transcript


def get_text_in_range(
    transcript: TranscriptResult, start: float, end: float
) -> list[TranscriptSegment]:
    """Return only the segments that overlap [start, end]."""
    return [
        s for s in transcript.segments
        if s.end > start and s.start < end
    ]


def get_words_in_range(
    transcript: TranscriptResult, start: float, end: float
) -> list[dict]:
    """Return word-level items that fall within [start, end]."""
    result = []
    for seg in transcript.segments:
        for word in seg.words:
            if word["end"] > start and word["start"] < end:
                result.append(word)
    return result
