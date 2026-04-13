"""
Video clipping and reformatting module.
Cuts source video to clip boundaries and reformats to 9:16 (1080×1920) vertical.
Supports watermark/logo overlay via ffmpeg filter_complex.
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
    WATERMARK_MARGIN,
    WATERMARK_OPACITY,
    WATERMARK_PATH,
    WATERMARK_POSITION,
    WATERMARK_WIDTH,
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
        return (1920, 1080)
    parts = result.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])


def _detect_face_center(video_path: Path, timestamp: float) -> Optional[tuple[int, int]]:
    """Use OpenCV to detect the dominant face in a frame. Returns None if unavailable."""
    try:
        import cv2
    except ImportError:
        return None

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(timestamp * fps))
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

    faces_sorted = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    x, y, w, h = faces_sorted[0]
    logger.debug(f"Face detected at ({x + w // 2}, {y + h // 2})")
    return (x + w // 2, y + h // 2)


def _logo_position_expr(position: str, margin: int) -> tuple[str, str]:
    """
    Return ffmpeg (x, y) overlay expressions for the given position string.
    Uses W/H (output dimensions) and w/h (logo dimensions).
    """
    m = margin
    positions = {
        "top-left":     (f"{m}",       f"{m}"),
        "top-right":    (f"W-w-{m}",   f"{m}"),
        "bottom-left":  (f"{m}",       f"H-h-{m}"),
        "bottom-right": (f"W-w-{m}",   f"H-h-{m}"),
    }
    return positions.get(position, (f"{m}", f"{m}"))


def _build_filtergraph(
    src_w: int,
    src_h: int,
    face_center: Optional[tuple[int, int]],
    ass_file: Optional[Path],
    logo_path: Optional[Path],
    logo_input_idx: int = 1,
) -> tuple[str, bool]:
    """
    Build the complete ffmpeg filtergraph.

    Returns:
        (filter_string, use_filter_complex)
        - use_filter_complex=True  → use -filter_complex + -map "[out]"
        - use_filter_complex=False → use -vf
    """
    target_w = OUTPUT_WIDTH    # 1080
    target_h = OUTPUT_HEIGHT   # 1920
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    use_complex = (logo_path is not None) or (
        ass_file is not None and src_ratio > target_ratio
    )

    # ── Base video filter ─────────────────────────────────────────────────────
    if src_ratio <= target_ratio:
        # Portrait/square source → simple scale + pad
        base = (
            f"[0:v]scale={target_w}:-2,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={OUTPUT_FPS}[base]"
        )
    else:
        # Landscape source → blur background + foreground crop
        crop_w = int(src_h * target_ratio)
        crop_h = src_h
        crop_x = (
            max(0, min(face_center[0] - crop_w // 2, src_w - crop_w))
            if face_center else (src_w - crop_w) // 2
        )
        base = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},"
            f"gblur=sigma=30[bg];"
            f"[0:v]crop={crop_w}:{crop_h}:{crop_x}:0,"
            f"scale={target_w}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
            f"fps={OUTPUT_FPS}[base]"
        )

    # ── Subtitle filter ────────────────────────────────────────────────────────
    after_subs = "[base]"
    subs_part = ""
    if ass_file and ass_file.exists():
        escaped = str(ass_file).replace("\\", "/")
        # On Windows, drive letter colon must be escaped for ffmpeg filter
        if len(escaped) > 1 and escaped[1] == ":":
            escaped = escaped[0] + "\\:" + escaped[2:]
        subs_part = f"[base]subtitles='{escaped}'[subbed]"
        after_subs = "[subbed]"

    # ── Logo filter ────────────────────────────────────────────────────────────
    logo_part = ""
    out_label = after_subs
    if logo_path and logo_path.exists():
        lx, ly = _logo_position_expr(WATERMARK_POSITION, WATERMARK_MARGIN)
        alpha = max(0.0, min(1.0, WATERMARK_OPACITY))
        logo_part = (
            f"[{logo_input_idx}:v]"
            f"scale={WATERMARK_WIDTH}:-1,"
            f"format=rgba,"
            f"colorchannelmixer=aa={alpha:.2f}"
            f"[logo];"
            f"{after_subs}[logo]overlay={lx}:{ly}[out]"
        )
        out_label = "[out]"

    # ── Assemble ──────────────────────────────────────────────────────────────
    if not use_complex and not subs_part and not logo_part:
        # Simple -vf mode: strip leading [0:v] tag and trailing [base] tag
        simple = base.replace("[0:v]", "").rstrip("[base]").rstrip(";")
        # For the landscape blur case we still need filter_complex
        if ";" in base:
            use_complex = True
        else:
            return simple, False

    parts = [p for p in [base, subs_part, logo_part] if p]
    filter_str = ";".join(parts)
    return filter_str, True


def cut_and_format(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    ass_file: Optional[Path] = None,
    logo_path: Optional[Path] = None,
) -> Path:
    """
    Cut video from *start_time* to *end_time*, reformat to 1080×1920 vertical,
    optionally burn subtitles and overlay a watermark logo.

    Args:
        video_path:  Source video file.
        start_time:  Clip start in seconds.
        end_time:    Clip end in seconds.
        output_path: Destination MP4 path.
        ass_file:    Optional .ass subtitle file to burn in.
        logo_path:   Optional logo image (PNG with transparency recommended).

    Returns:
        Path to the generated clip file.

    Raises:
        ClipError: On any ffmpeg failure.
    """
    if not shutil.which("ffmpeg"):
        raise ClipError("ffmpeg is not installed or not found in PATH.")

    padded_start = max(0.0, start_time - CLIP_PADDING_SECONDS)
    padded_end = end_time + CLIP_PADDING_SECONDS
    duration = padded_end - padded_start
    output_path.parent.mkdir(parents=True, exist_ok=True)

    src_w, src_h = _ffprobe_dimensions(video_path)
    midpoint = padded_start + duration / 2
    face_center = _detect_face_center(video_path, midpoint)

    # Resolve effective logo path (config fallback)
    effective_logo = logo_path or WATERMARK_PATH
    if effective_logo and not effective_logo.exists():
        logger.warning(f"Logo file not found, skipping watermark: {effective_logo}")
        effective_logo = None

    filter_str, use_complex = _build_filtergraph(
        src_w=src_w,
        src_h=src_h,
        face_center=face_center,
        ass_file=ass_file,
        logo_path=effective_logo,
        logo_input_idx=1,
    )

    # Build ffmpeg arguments
    cmd_args: list[str] = [
        "-ss", str(padded_start),
        "-i", str(video_path),
    ]

    if effective_logo:
        cmd_args += ["-i", str(effective_logo)]

    if use_complex:
        # Determine the output label
        out_label = "[out]" if effective_logo else ("[subbed]" if ass_file else "[base]")
        cmd_args += ["-filter_complex", filter_str, "-map", out_label]
    else:
        cmd_args += ["-vf", filter_str]

    cmd_args += [
        "-t", str(duration),
        "-c:v", OUTPUT_CODEC,
        "-preset", OUTPUT_PRESET,
        "-crf", str(OUTPUT_CRF),
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    _ffmpeg(*cmd_args)
    logger.info(
        f"Clip saved → {output_path} ({duration:.1f}s)"
        + (f" [logo: {effective_logo.name}]" if effective_logo else "")
    )
    return output_path


def generate_thumbnail(video_path: Path, thumbnail_path: Path, timestamp: float = 1.0) -> Path:
    """Extract a frame from *video_path* as a JPEG thumbnail."""
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
    slug = slugify(title)
    return CLIPS_DIR / f"{video_id}_{clip_index:02d}_{slug}.mp4"


def build_thumbnail_path(clip_path: Path) -> Path:
    return clip_path.with_suffix(".jpg")


def process_clip(
    video_path: Path,
    video_id: str,
    clip_index: int,
    title: str,
    start_time: float,
    end_time: float,
    ass_file: Optional[Path] = None,
    logo_path: Optional[Path] = None,
) -> tuple[Path, Path]:
    """
    Full pipeline: cut → vertical reformat → subtitles → logo → thumbnail.

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

    cut_and_format(
        video_path=video_path,
        start_time=start_time,
        end_time=end_time,
        output_path=output_path,
        ass_file=ass_file,
        logo_path=logo_path,
    )

    try:
        generate_thumbnail(output_path, thumbnail_path, timestamp=1.0)
    except ClipError as e:
        logger.warning(f"Thumbnail generation failed: {e}")

    return output_path, thumbnail_path
