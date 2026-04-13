"""
Viral moment analyzer using the Claude API.
Identifies high-potential clips from a transcript.
"""

import json
import logging
import re
from typing import Optional

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLIP_MAX_DURATION,
    CLIP_MIN_DURATION,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODEL,
    MAX_CLIPS_PER_VIDEO,
    TRANSCRIPT_CHUNK_SIZE,
)
from transcriber import TranscriptResult

logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    """Raised when analysis fails."""


class ClipCandidate:
    """A single viral clip candidate returned by the analyzer."""

    def __init__(
        self,
        title: str,
        hook: str,
        start_time: float,
        end_time: float,
        viral_score: float,
        category: str,
        reasoning: str,
        suggested_caption: str = "",
    ) -> None:
        self.title = title
        self.hook = hook
        self.start_time = round(start_time, 2)
        self.end_time = round(end_time, 2)
        self.duration = round(end_time - start_time, 2)
        self.viral_score = viral_score
        self.category = category
        self.reasoning = reasoning
        self.suggested_caption = suggested_caption

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "hook": self.hook,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "viral_score": self.viral_score,
            "category": self.category,
            "reasoning": self.reasoning,
            "suggested_caption": self.suggested_caption,
        }


# ─── Prompt Construction ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert YouTube Shorts and TikTok content strategist.
Your job is to analyze video transcripts and identify moments with maximum viral potential.

You deeply understand:
- What makes content stop the scroll (pattern interrupts, emotional hooks)
- Punchlines, reveals, and narrative peaks
- Self-contained moments that work without prior context
- The psychology of sharing (surprise, humor, outrage, inspiration, drama)
- Short-form video retention patterns

Always respond with valid JSON matching the schema requested. No extra text outside JSON."""

_ANALYSIS_PROMPT_TEMPLATE = """Analyze this video transcript and identify the {max_clips} best moments for YouTube Shorts/TikTok clips.

VIDEO METADATA:
- Title: {title}
- Channel: {channel}
- Duration: {duration_str}
- Language: {language}

{learning_context}

TRANSCRIPT (with timestamps in seconds):
{transcript_text}

REQUIREMENTS:
- Each clip must be {min_dur}–{max_dur} seconds long
- Clips must NOT cut in the middle of sentences
- Each clip needs a strong hook in the first 3 seconds
- Prioritize moments that are self-contained (make sense without context)

VIRAL CATEGORIES to look for:
1. humor — genuinely funny moments, comedic timing, unexpected jokes
2. shock — surprising facts, dramatic reveals, plot twists
3. insight — valuable lessons, "aha" moments, expert knowledge
4. drama — conflict, tension, emotional peaks
5. motivation — inspiring, empowering, relatable struggle
6. controversy — strong opinions, debate-worthy takes, polarizing statements

For each clip, provide a viral_score from 1.0 to 10.0 based on:
- Hook strength (first 3 seconds) — 30%
- Emotional impact — 25%
- Self-containment (no context needed) — 20%
- Shareability — 15%
- Retention likelihood — 10%

Return ONLY a JSON object in this exact format:
{{
  "clips": [
    {{
      "title": "Short catchy title for the YouTube Shorts video",
      "hook": "The exact opening line/moment that serves as the hook",
      "start_time": 125.3,
      "end_time": 183.7,
      "viral_score": 8.5,
      "category": "humor",
      "reasoning": "1-2 sentences explaining why this moment has viral potential",
      "suggested_caption": "Caption text for the Short with relevant hashtags"
    }}
  ]
}}

Order clips by viral_score descending."""


def _build_transcript_text(transcript: TranscriptResult) -> str:
    """Format the transcript for inclusion in the prompt."""
    lines = []
    for seg in transcript.segments:
        lines.append(f"[{seg.start:.1f}s] {seg.text}")
    return "\n".join(lines)


def _build_prompt(
    transcript: TranscriptResult,
    metadata: dict,
    learning_profile: Optional[dict] = None,
    max_clips: int = MAX_CLIPS_PER_VIDEO,
) -> str:
    """Assemble the full user prompt."""
    duration_secs = metadata.get("duration", 0)
    minutes, seconds = divmod(int(duration_secs), 60)
    duration_str = f"{minutes}m {seconds}s"

    learning_context = ""
    if learning_profile and learning_profile.get("total_clips_rated", 0) >= 5:
        profile_data = learning_profile.get("profile_data", learning_profile)
        if isinstance(profile_data, dict) and "profile_data" in profile_data:
            profile_data = profile_data["profile_data"]
        rules = profile_data.get("learned_rules", [])
        best_cats = profile_data.get("best_performing_categories", [])
        opt_dur = profile_data.get("optimal_duration_range", [])
        if rules or best_cats:
            lines = ["PERSONALIZED INSIGHTS FROM PAST PERFORMANCE (apply these):"]
            if best_cats:
                lines.append(f"- Best-performing categories: {', '.join(best_cats)}")
            if opt_dur and len(opt_dur) == 2:
                lines.append(f"- Optimal clip duration: {opt_dur[0]}–{opt_dur[1]} seconds")
            for rule in rules[:5]:
                lines.append(f"- {rule}")
            learning_context = "\n".join(lines) + "\n"

    transcript_text = _build_transcript_text(transcript)

    # Chunk if too long
    if len(transcript_text) > TRANSCRIPT_CHUNK_SIZE:
        transcript_text = transcript_text[:TRANSCRIPT_CHUNK_SIZE] + "\n[...transcript truncated for length]"

    return _ANALYSIS_PROMPT_TEMPLATE.format(
        max_clips=max_clips,
        title=metadata.get("title", "Unknown"),
        channel=metadata.get("uploader", "Unknown"),
        duration_str=duration_str,
        language=transcript.language or "unknown",
        learning_context=learning_context,
        transcript_text=transcript_text,
        min_dur=CLIP_MIN_DURATION,
        max_dur=CLIP_MAX_DURATION,
    )


def _parse_response(raw: str) -> list[dict]:
    """Extract and parse the JSON clips array from Claude's response."""
    # Strip markdown code fences if present
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to extract JSON object with regex as fallback
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                raise AnalysisError(f"Could not parse Claude response as JSON: {e}") from e
        else:
            raise AnalysisError(f"No JSON found in Claude response: {e}") from e

    clips = data.get("clips", [])
    if not isinstance(clips, list):
        raise AnalysisError("Expected 'clips' to be a list in Claude response")
    return clips


def _validate_and_filter(clips: list[dict], video_duration: float) -> list[ClipCandidate]:
    """Validate clip boundaries and filter out invalid candidates."""
    valid: list[ClipCandidate] = []
    for raw in clips:
        try:
            start = float(raw["start_time"])
            end = float(raw["end_time"])
            duration = end - start

            if duration < CLIP_MIN_DURATION:
                logger.debug(f"Clip too short ({duration:.1f}s), skipping: {raw.get('title')}")
                continue
            if duration > CLIP_MAX_DURATION:
                logger.debug(f"Clip too long ({duration:.1f}s), skipping: {raw.get('title')}")
                continue
            if start < 0:
                start = 0.0
            if video_duration and end > video_duration:
                end = video_duration

            valid.append(
                ClipCandidate(
                    title=raw.get("title", "Untitled Clip"),
                    hook=raw.get("hook", ""),
                    start_time=start,
                    end_time=end,
                    viral_score=float(raw.get("viral_score", 5.0)),
                    category=raw.get("category", "insight"),
                    reasoning=raw.get("reasoning", ""),
                    suggested_caption=raw.get("suggested_caption", ""),
                )
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed clip candidate: {e} — {raw}")

    # Sort by viral score descending
    valid.sort(key=lambda c: c.viral_score, reverse=True)
    return valid


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze(
    transcript: TranscriptResult,
    metadata: dict,
    learning_profile: Optional[dict] = None,
    max_clips: int = MAX_CLIPS_PER_VIDEO,
) -> list[ClipCandidate]:
    """
    Analyze *transcript* using Claude and return ranked clip candidates.

    Args:
        transcript:       Full transcription result with word timestamps.
        metadata:         Video metadata dict (title, channel, duration …).
        learning_profile: Optional learned preferences from past feedback.
        max_clips:        Maximum number of clips to request.

    Returns:
        List of ClipCandidate objects sorted by viral_score descending.

    Raises:
        AnalysisError: On API errors or unparseable responses.
    """
    if not ANTHROPIC_API_KEY:
        raise AnalysisError(
            "ANTHROPIC_API_KEY is not set. Please add it to your .env file."
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(transcript, metadata, learning_profile, max_clips)

    logger.info(
        f"[{transcript.video_id}] Sending transcript to Claude "
        f"({len(prompt)} chars) …"
    )

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise AnalysisError("Invalid Anthropic API key. Check your ANTHROPIC_API_KEY.")
    except anthropic.RateLimitError:
        raise AnalysisError("Anthropic rate limit exceeded. Please wait and retry.")
    except anthropic.APIError as e:
        raise AnalysisError(f"Anthropic API error: {e}") from e

    raw_response = message.content[0].text
    logger.debug(f"[{transcript.video_id}] Raw Claude response:\n{raw_response[:500]}")

    raw_clips = _parse_response(raw_response)
    candidates = _validate_and_filter(raw_clips, float(metadata.get("duration", 0)))

    logger.info(
        f"[{transcript.video_id}] Analysis complete — "
        f"{len(candidates)} valid clip candidates (requested {max_clips})"
    )
    return candidates[:max_clips]
