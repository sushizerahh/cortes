"""
Subtitle generation module.
Burns karaoke-style word-by-word subtitles into clips using ASS format.
"""

import logging
import textwrap
from pathlib import Path
from typing import Optional

from config import CLIPS_DIR, SUBTITLE_STYLES
from utils import ass_timestamp

logger = logging.getLogger(__name__)


class SubtitleError(Exception):
    """Raised when subtitle generation fails."""


# ─── ASS Header ───────────────────────────────────────────────────────────────

_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary},{secondary},{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_size},{shadow},2,80,80,{margin_v},1
Style: Highlight,{font},{font_size},{highlight},{secondary},{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_size},{shadow},2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _hex_to_ass_color(css_hex: str) -> str:
    """
    Convert a CSS hex color (#RRGGBB) to ASS &HAABBGGRR format.
    If already in ASS format (&H…), return as-is.
    """
    if css_hex.startswith("&H"):
        return css_hex
    css_hex = css_hex.lstrip("#")
    if len(css_hex) == 6:
        r, g, b = css_hex[0:2], css_hex[2:4], css_hex[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"


def _build_ass_header(style_name: str) -> str:
    """Generate the ASS script header with the chosen style."""
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["default"])

    # Calculate margin_v: place text at ~72% of 1920px height
    margin_v = int(1920 * 0.28)  # 28% from bottom ≈ 72% from top

    return _ASS_HEADER.format(
        font=style["font"],
        font_size=style["font_size"],
        primary=style["primary_color"],
        secondary=style["primary_color"],
        outline=style["outline_color"],
        back="&H80000000",  # semi-transparent black back
        highlight=style["highlight_color"],
        bold=-1 if style["bold"] else 0,
        outline_size=style["outline_size"],
        shadow=style["shadow"],
        margin_v=margin_v,
    )


# ─── Word grouping ────────────────────────────────────────────────────────────

def _group_words(
    words: list[dict],
    words_per_group: int,
    clip_start: float,
) -> list[dict]:
    """
    Group words into display chunks and return a list of groups.
    Each group has: start, end, text, highlight_idx (index of currently spoken word).

    The 'highlight_idx' cycles through the words in the group so that each word
    gets highlighted while it is being spoken.
    """
    if not words:
        return []

    # Offset timestamps relative to clip start
    shifted = []
    for w in words:
        shifted.append({
            "word": w["word"],
            "start": round(w["start"] - clip_start, 3),
            "end": round(w["end"] - clip_start, 3),
        })

    # Split into fixed-size groups
    groups = []
    for i in range(0, len(shifted), words_per_group):
        chunk = shifted[i: i + words_per_group]
        group_start = chunk[0]["start"]
        group_end = chunk[-1]["end"]
        groups.append({
            "words": chunk,
            "group_start": group_start,
            "group_end": group_end,
        })
    return groups


def _build_dialogue_events(
    groups: list[dict],
    words_per_group: int,
    style_name: str,
) -> list[str]:
    """
    Generate ASS Dialogue lines for each word group.
    Each word within a group gets its own highlight line while being spoken;
    the remaining words show in the Default style simultaneously.
    """
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["default"])
    lines: list[str] = []

    for group in groups:
        words = group["words"]
        group_text = " ".join(w["word"] for w in words)

        # One line per word: highlight the spoken word, rest in Default color
        for wi, word_info in enumerate(words):
            w_start = max(0.0, word_info["start"])
            w_end = max(w_start + 0.05, word_info["end"])

            # Build text with karaoke highlight using override tags
            parts = []
            for j, w in enumerate(words):
                if j == wi:
                    # Active word — Highlight style color inline
                    parts.append(
                        f"{{\\c{style['highlight_color']}\\3c{style['outline_color']}}}"
                        f"{w['word']}"
                        f"{{\\c{style['primary_color']}\\3c{style['outline_color']}}}"
                    )
                else:
                    parts.append(w["word"])

            dialogue_text = " ".join(parts)

            line = (
                f"Dialogue: 0,{ass_timestamp(w_start)},{ass_timestamp(w_end)},"
                f"Default,,0,0,0,,{dialogue_text}"
            )
            lines.append(line)

        # Also add a "background" line showing the entire group for the full duration
        # so there is never a gap between word highlights
        bg_text = "{\\alpha&H40&}" + group_text + "{\\alpha&H00&}"
        bg_line = (
            f"Dialogue: 0,{ass_timestamp(group['group_start'])},"
            f"{ass_timestamp(group['group_end'])},Default,,0,0,0,,{group_text}"
        )
        # We actually skip the bg line since the per-word lines cover the group
        # The above block already paints text continuously.

    return lines


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_ass(
    words: list[dict],
    clip_start: float,
    clip_end: float,
    output_path: Path,
    style_name: str = "default",
) -> Path:
    """
    Generate an ASS subtitle file for a clip.

    Args:
        words:        Word-level items [{word, start, end}, ...] with absolute timestamps.
        clip_start:   Clip start time in seconds (to offset timestamps).
        clip_end:     Clip end time in seconds.
        output_path:  Where to write the .ass file.
        style_name:   One of 'default', 'neon', 'minimal', 'bold'.

    Returns:
        Path to the generated .ass file.

    Raises:
        SubtitleError: On any failure.
    """
    if not words:
        raise SubtitleError("No words provided for subtitle generation.")

    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["default"])
    words_per_group: int = style["words_per_group"]

    # Filter to words within the clip range
    clip_words = [
        w for w in words
        if w["end"] > clip_start and w["start"] < clip_end
    ]
    if not clip_words:
        raise SubtitleError("No words fall within the clip time range.")

    groups = _group_words(clip_words, words_per_group, clip_start)
    header = _build_ass_header(style_name)
    dialogue_events = _build_dialogue_events(groups, words_per_group, style_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for line in dialogue_events:
            f.write(line + "\n")

    logger.info(
        f"ASS subtitle file written -> {output_path} "
        f"({len(clip_words)} words, {len(groups)} groups, style={style_name!r})"
    )
    return output_path


def ass_path_for_clip(video_id: str, clip_index: int) -> Path:
    """Return the conventional .ass file path for a clip."""
    return CLIPS_DIR / f"{video_id}_{clip_index:02d}.ass"


def generate_for_clip(
    all_words: list[dict],
    clip_start: float,
    clip_end: float,
    video_id: str,
    clip_index: int,
    style_name: str = "default",
) -> Optional[Path]:
    """
    Convenience wrapper: generate ASS file for a clip.

    Returns:
        Path to the .ass file, or None if word list is empty.
    """
    if not all_words:
        logger.warning("No word-level timestamps available — subtitles will be skipped.")
        return None

    out = ass_path_for_clip(video_id, clip_index)
    try:
        return generate_ass(all_words, clip_start, clip_end, out, style_name)
    except SubtitleError as e:
        logger.error(f"Subtitle generation failed for clip {clip_index}: {e}")
        return None
