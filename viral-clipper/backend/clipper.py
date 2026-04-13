"""
Video clipping and reformatting module.
Cuts source video to clip boundaries and reformats to 9:16 (1080×1920) vertical.
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from config import (
    CLIP_PADDING_SECONDS,
    CLIPS_DIR,
    OUTPUT_CODEC,
    OUTPUT_CRF,
    OUTPUT_FPS,
    OUTPUT_HEIGHT,
    OUTPUT_PRESET,
    OUTPUT_WIDTH,
)
from utils import slugify

logger = logging.getLogger(__name__)


class ClipError(Exception):
    """Raised when clipping fails."""


def _ffmpeg(*args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run ffmpeg with the given arguments, raising ClipError on failure."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    logger.debug(f"ffmpeg: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ClipError(f"ffmpeg error:\n{result.stderr}")
    return result


def _ffprobe_dimensions(video_path: Path) -> tuple[int, int]:
    """Return (width, height) of the video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or not result.stdout.strip():
        return (1920, 1080)  # Assume 1080p landscape as fallback
    parts = result.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])


def _detect_face_center(video_path: Path, timestamp: float) -> Optional[tuple[int, int]]:
    """
    Use OpenCV to detect the dominant face in a frame and return its center (x, y).
    Returns None if OpenCV is unavailable or no face is detected.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_idx = int(timestamp * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        return None

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

    if len(faces) == 0:
        return None

    # Pick the largest face
    faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = faces_sorted[0]
    center_x = x + w // 2
    center_y = y + h // 2
    logger.debug(f"Face detected at ({center_x}, {center_y})")
    return (center_x, center_y)


def _build_vertical_filter(
    src_w: int,
    src_h: int,
    face_center: Optional[tuple[int, int]] = None,
) -> str:
    """
    Build an ffmpeg filtergraph string that converts a source frame of (src_w × src_h)
    to 1080×1920 vertical format using one of these strategies:

    1. If source is already taller than wide → pad/scale directly.
    2. If source is landscape (wider than tall):
       a. Smart crop centered on face (if detected)
       b. Centered crop otherwise
       Blurred-background fill for letterboxing edges.
    """
    target_w = OUTPUT_WIDTH    # 1080
    target_h = OUTPUT_HEIGHT   # 1920
    target_ratio = target_w / target_h  # 9/16 ≈ 0.5625

    src_ratio = src_w / src_h

    if src_ratio <= target_ratio:
        # Already portrait-ish — scale and pad vertically
        return (
            f"scale={target_w}:-2,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={OUTPUT_FPS}"
        )

    # Landscape source → crop to 9:16
    # Crop width from height: crop_w = src_h * (9/16)
    crop_w = int(src_h * target_ratio)
    crop_h = src_h

    if face_center:
        cx = face_center[0]
        # Center crop on face, clamp to valid range
        crop_x = max(0, min(cx - crop_w // 2, src_w - crop_w))
    else:
        crop_x = (src_w - crop_w) // 2
    crop_y = 0

    # Blurred background approach: scale full frame to target, blur it,
    # then overlay the cropped+scaled foreground centred on top.
    blur_filter = (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"gblur=sigma=30[bg];"
        f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={target_w}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"fps={OUTPUT_FPS}"
    )
    return blur_filter


def cut_and_format(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    subtitle_filter: Optional[str] = None,
) -> Path:
    """
    Cut video from *start_time* to *end_time* and reformat to 1080×1920 vertical.

    Args:
        video_path:      Source video file.
        start_time:      Clip start in seconds (with padding already applied).
        end_time:        Clip end in seconds.
        output_path:     Destination MP4 path.
        subtitle_filter: Optional ffmpeg drawtext / ASS filter string to burn in.

    Returns:
        Path to the generated clip file.

    Raises:
        ClipError: On any ffmpeg failure.
    """
    if not shutil.which("ffmpeg"):
        raise ClipError("ffmpeg is not installed or not found in PATH.")

    # Apply padding
    padded_start = max(0.0, start_time - CLIP_PADDING_SECONDS)
    padded_end = end_time + CLIP_PADDING_SECONDS

    duration = padded_end - padded_start
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect source dimensions
    src_w, src_h = _ffprobe_dimensions(video_path)
    logger.debug(f"Source dimensions: {src_w}×{src_h}")

    # Try face detection at midpoint
    midpoint = padded_start + duration / 2
    face_center = _detect_face_center(video_path, midpoint)

    vf = _build_vertical_filter(src_w, src_h, face_center)

    if subtitle_filter:
        vf = f"{vf},{subtitle_filter}" if ";" not in vf else f"{vf}[out];[out]{subtitle_filter}"

    _ffmpeg(
        "-ss", str(padded_start),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", OUTPUT_CODEC,
        "-preset", OUTPUT_PRESET,
        "-crf", str(OUTPUT_CRF),
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    )

    logger.info(f"Clip saved → {output_path} ({duration:.1f}s)")
    return output_path


def generate_thumbnail(video_path: Path, thumbnail_path: Path, timestamp: float = 1.0) -> Path:
    """
    Extract a single frame from *video_path* at *timestamp* seconds as a JPEG thumbnail.

    Returns:
        Path to the thumbnail file.
    """
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(thumbnail_path),
    )
    logger.debug(f"Thumbnail saved → {thumbnail_path}")
    return thumbnail_path


def build_clip_output_path(video_id: str, clip_index: int, title: str) -> Path:
    """Return a standardized output path for a clip."""
    slug = slugify(title)
    return CLIPS_DIR / f"{video_id}_{clip_index:02d}_{slug}.mp4"


def build_thumbnail_path(clip_path: Path) -> Path:
    """Return the thumbnail path corresponding to a clip path."""
    return clip_path.with_suffix(".jpg")


def process_clip(
    video_path: Path,
    video_id: str,
    clip_index: int,
    title: str,
    start_time: float,
    end_time: float,
    ass_file: Optional[Path] = None,
) -> tuple[Path, Path]:
    """
    Full pipeline: cut, format vertical, burn subtitles (if provided), generate thumbnail.

    Returns:
        Tuple of (clip_path, thumbnail_path).
    """
    output_path = build_clip_output_path(video_id, clip_index, title)
    thumbnail_path = build_thumbnail_path(output_path)

    if output_path.exists():
        logger.info(f"Clip already exists, skipping: {output_path}")
        if not thumbnail_path.exists():
            generate_thumbnail(output_path, thumbnail_path)
        return output_path, thumbnail_path

    # Build subtitle filter if ASS file provided
    subtitle_filter = None
    if ass_file and ass_file.exists():
        # Use the subtitles filter — escape path for ffmpeg
        escaped = str(ass_file).replace("\\", "/").replace(":", "\\:")
        subtitle_filter = f"subtitles='{escaped}'"

    cut_and_format(
        video_path=video_path,
        start_time=start_time,
        end_time=end_time,
        output_path=output_path,
        subtitle_filter=subtitle_filter,
    )

    # Generate thumbnail from 1 second into the clip
    try:
        generate_thumbnail(output_path, thumbnail_path, timestamp=1.0)
    except ClipError as e:
        logger.warning(f"Thumbnail generation failed: {e}")

    return output_path, thumbnail_path
