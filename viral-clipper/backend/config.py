"""
Global configuration for ViralClipper.
Loads settings from .env file and provides typed access to all config values.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ─── Base Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
CLIPS_DIR = DATA_DIR / "clips"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
DB_PATH = DATA_DIR / "viral_clipper.db"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
for _dir in [DATA_DIR, DOWNLOADS_DIR, CLIPS_DIR, TRANSCRIPTS_DIR, LOG_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ─── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# ─── Whisper ──────────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "medium")

# ─── Clip Settings ────────────────────────────────────────────────────────────
CLIP_MIN_DURATION: int = int(os.getenv("CLIP_MIN_DURATION", "15"))
CLIP_MAX_DURATION: int = int(os.getenv("CLIP_MAX_DURATION", "59"))
MAX_CLIPS_PER_VIDEO: int = int(os.getenv("MAX_CLIPS_PER_VIDEO", "10"))

# ─── Subtitle Settings ────────────────────────────────────────────────────────
DEFAULT_SUBTITLE_STYLE: str = os.getenv("DEFAULT_SUBTITLE_STYLE", "default")

SUBTITLE_STYLES = {
    "default": {
        "font": "Arial",
        "font_size": 72,
        "primary_color": "&H00FFFFFF",    # White
        "outline_color": "&H00000000",    # Black outline
        "highlight_color": "&H0000FFFF",  # Yellow highlight
        "outline_size": 4,
        "shadow": 2,
        "bold": True,
        "words_per_group": 3,
    },
    "neon": {
        "font": "Arial",
        "font_size": 72,
        "primary_color": "&H0000FF88",    # Neon green
        "outline_color": "&H00004400",    # Dark green outline
        "highlight_color": "&H00FF00FF",  # Magenta highlight
        "outline_size": 3,
        "shadow": 3,
        "bold": True,
        "words_per_group": 3,
    },
    "minimal": {
        "font": "Arial",
        "font_size": 60,
        "primary_color": "&H00FFFFFF",    # White
        "outline_color": "&H00000000",    # Black outline
        "highlight_color": "&H00FFFFFF",  # No highlight (same as primary)
        "outline_size": 2,
        "shadow": 1,
        "bold": False,
        "words_per_group": 4,
    },
    "bold": {
        "font": "Arial",
        "font_size": 90,
        "primary_color": "&H00FFFFFF",    # White
        "outline_color": "&H00000000",    # Black
        "highlight_color": "&H000000FF",  # Red highlight
        "outline_size": 6,
        "shadow": 0,
        "bold": True,
        "words_per_group": 2,
    },
}

# ─── Video Output ─────────────────────────────────────────────────────────────
OUTPUT_WIDTH: int = 1080
OUTPUT_HEIGHT: int = 1920
OUTPUT_FPS: int = 30
OUTPUT_CODEC: str = "libx264"
OUTPUT_PRESET: str = "slow"
OUTPUT_CRF: int = 18
CLIP_PADDING_SECONDS: float = 0.5

# ─── Claude API ───────────────────────────────────────────────────────────────
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
CLAUDE_MAX_TOKENS: int = 4096
TRANSCRIPT_CHUNK_SIZE: int = 50000  # characters per chunk

# ─── API Server ───────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "3000"))
CORS_ORIGINS: list[str] = [
    f"http://localhost:{FRONTEND_PORT}",
    f"http://127.0.0.1:{FRONTEND_PORT}",
    "http://localhost:3000",
    "http://localhost:5173",
]

# ─── Watermark / Logo ─────────────────────────────────────────────────────────
# Path to your logo PNG file (transparent background recommended)
_wm_path = os.getenv("WATERMARK_PATH", "")
WATERMARK_PATH: Optional[Path] = Path(_wm_path) if _wm_path else None

# Position: top-left | top-right | bottom-left | bottom-right
WATERMARK_POSITION: str = os.getenv("WATERMARK_POSITION", "top-left")

# Logo width in pixels (height is auto-calculated to preserve aspect ratio)
WATERMARK_WIDTH: int = int(os.getenv("WATERMARK_WIDTH", "220"))

# Opacity from 0.0 (invisible) to 1.0 (fully opaque)
WATERMARK_OPACITY: float = float(os.getenv("WATERMARK_OPACITY", "1.0"))

# Margin from the edge in pixels
WATERMARK_MARGIN: int = int(os.getenv("WATERMARK_MARGIN", "30"))

# ─── Download ─────────────────────────────────────────────────────────────────
MAX_VIDEO_QUALITY: str = "1080"
AUDIO_FORMAT: str = "wav"

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Path = LOG_DIR / "viralclipper.log"
