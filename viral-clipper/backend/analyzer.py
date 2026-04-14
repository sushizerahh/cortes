"""
Viral moment analyzer — supports multiple LLM providers:
  anthropic (Claude), groq (Llama, free), gemini (Google, free), ollama (local, free)
Set LLM_PROVIDER in .env to choose.
"""

import json
import logging
import re
from typing import Optional

from config import (
    ANTHROPIC_API_KEY,
    CLIP_MAX_DURATION,
    CLIP_MIN_DURATION,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    CLAUDE_MODEL,
    LLM_MAX_TOKENS,
    LLM_PROVIDER,
    MAX_CLIPS_PER_VIDEO,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    TRANSCRIPT_CHUNK_SIZE,
)
from transcriber import TranscriptResult

logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    """Raised when analysis fails."""


# ─── Prompts ──────────────────────────────────────────────────────────────────

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
- Each clip must be {min_dur}-{max_dur} seconds long
- Clips must NOT cut in the middle of sentences
- Each clip needs a strong hook in the first 3 seconds
- Prioritize moments that are self-contained (make sense without context)

VIRAL CATEGORIES to look for:
1. humor - genuinely funny moments, comedic timing, unexpected jokes
2. shock - surprising facts, dramatic reveals, plot twists
3. insight - valuable lessons, "aha" moments, expert knowledge
4. drama - conflict, tension, emotional peaks
5. motivation - inspiring, empowering, relatable struggle
6. controversy - strong opinions, debate-worthy takes, polarizing statements

For each clip, provide a viral_score from 1.0 to 10.0 based on:
- Hook strength (first 3 seconds) - 30%
- Emotional impact - 25%
- Self-containment (no context needed) - 20%
- Shareability - 15%
- Retention likelihood - 10%

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


# ─── Prompt helpers ───────────────────────────────────────────────────────────

def _build_transcript_text(transcript: TranscriptResult) -> str:
    lines = []
    for seg in transcript.segments:
        lines.append(f"[{seg.start:.1f}s] {seg.text}")
    return "\n".join(lines)


def _build_prompt(
    transcript: TranscriptResult,
    metadata: dict,
    learning_profile: Optional[dict],
    max_clips: int,
) -> str:
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
        lines = ["PERSONALIZED INSIGHTS FROM PAST PERFORMANCE (apply these):"]
        if best_cats:
            lines.append(f"- Best-performing categories: {', '.join(best_cats)}")
        if opt_dur and len(opt_dur) == 2:
            lines.append(f"- Optimal clip duration: {opt_dur[0]}-{opt_dur[1]} seconds")
        for rule in rules[:5]:
            lines.append(f"- {rule}")
        if len(lines) > 1:
            learning_context = "\n".join(lines) + "\n"

    transcript_text = _build_transcript_text(transcript)
    if len(transcript_text) > TRANSCRIPT_CHUNK_SIZE:
        transcript_text = transcript_text[:TRANSCRIPT_CHUNK_SIZE] + "\n[...transcript truncated]"

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


# ─── Response parser ──────────────────────────────────────────────────────────

def _parse_response(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise AnalysisError(f"No valid JSON found in LLM response:\n{raw[:300]}")
    clips = data.get("clips", [])
    if not isinstance(clips, list):
        raise AnalysisError("Expected 'clips' list in LLM response")
    return clips


def _validate(clips: list[dict], video_duration: float) -> list["ClipCandidate"]:
    valid = []
    for raw in clips:
        try:
            start = float(raw["start_time"])
            end = float(raw["end_time"])
            dur = end - start
            if dur < CLIP_MIN_DURATION or dur > CLIP_MAX_DURATION:
                continue
            start = max(0.0, start)
            if video_duration and end > video_duration:
                end = video_duration
            valid.append(ClipCandidate(
                title=raw.get("title", "Untitled Clip"),
                hook=raw.get("hook", ""),
                start_time=start,
                end_time=end,
                viral_score=float(raw.get("viral_score", 5.0)),
                category=raw.get("category", "insight"),
                reasoning=raw.get("reasoning", ""),
                suggested_caption=raw.get("suggested_caption", ""),
            ))
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed clip: {e}")
    valid.sort(key=lambda c: c.viral_score, reverse=True)
    return valid


# ─── ClipCandidate ────────────────────────────────────────────────────────────

class ClipCandidate:
    def __init__(self, title, hook, start_time, end_time,
                 viral_score, category, reasoning, suggested_caption=""):
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


# ─── Provider implementations ─────────────────────────────────────────────────

def _call_anthropic(system: str, prompt: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise AnalysisError(
            "ANTHROPIC_API_KEY not set. Add it to .env or switch LLM_PROVIDER."
        )
    try:
        import anthropic as _anthropic
    except ImportError:
        raise AnalysisError("anthropic package not installed. Run: pip install anthropic")

    client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except _anthropic.AuthenticationError:
        raise AnalysisError(
            "Invalid Anthropic API key. Check ANTHROPIC_API_KEY in your .env."
        )
    except _anthropic.RateLimitError:
        raise AnalysisError("Anthropic rate limit exceeded. Wait and retry.")
    except _anthropic.APIError as e:
        raise AnalysisError(f"Anthropic API error: {e}") from e


def _call_groq(system: str, prompt: str) -> str:
    if not GROQ_API_KEY:
        raise AnalysisError(
            "GROQ_API_KEY not set. Get a free key at console.groq.com and add it to .env."
        )
    try:
        from groq import Groq
    except ImportError:
        raise AnalysisError("groq package not installed. Run: pip install groq")

    client = Groq(api_key=GROQ_API_KEY)
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=LLM_MAX_TOKENS,
            temperature=0.3,
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise AnalysisError(f"Groq API error: {e}") from e


def _call_gemini(system: str, prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise AnalysisError(
            "GEMINI_API_KEY not set. Get a free key at aistudio.google.com and add it to .env."
        )
    try:
        import google.generativeai as genai
    except ImportError:
        raise AnalysisError(
            "google-generativeai not installed. Run: pip install google-generativeai"
        )

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system,
    )
    try:
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        raise AnalysisError(f"Gemini API error: {e}") from e


def _call_ollama(system: str, prompt: str) -> str:
    """Call a locally running Ollama instance (completely free)."""
    try:
        import urllib.request
        import json as _json

        payload = _json.dumps({
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.3},
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = _json.loads(resp.read())
            return data["message"]["content"]
    except Exception as e:
        raise AnalysisError(
            f"Ollama error: {e}\n"
            f"Make sure Ollama is running (ollama serve) and model '{OLLAMA_MODEL}' is pulled."
        ) from e


_PROVIDERS = {
    "anthropic": _call_anthropic,
    "groq":      _call_groq,
    "gemini":    _call_gemini,
    "ollama":    _call_ollama,
}


# ─── Public API ───────────────────────────────────────────────────────────────

def analyze(
    transcript: TranscriptResult,
    metadata: dict,
    learning_profile: Optional[dict] = None,
    max_clips: int = MAX_CLIPS_PER_VIDEO,
) -> list[ClipCandidate]:
    """
    Analyze *transcript* using the configured LLM provider and return
    ranked clip candidates.

    Provider is selected via LLM_PROVIDER in .env:
      anthropic | groq | gemini | ollama
    """
    provider = LLM_PROVIDER.lower().strip()
    call_fn = _PROVIDERS.get(provider)
    if call_fn is None:
        raise AnalysisError(
            f"Unknown LLM_PROVIDER '{provider}'. "
            f"Choose from: {', '.join(_PROVIDERS)}"
        )

    prompt = _build_prompt(transcript, metadata, learning_profile, max_clips)
    logger.info(
        f"[{transcript.video_id}] Sending {len(prompt)} chars to "
        f"provider='{provider}' ..."
    )

    raw = call_fn(_SYSTEM_PROMPT, prompt)
    logger.debug(f"[{transcript.video_id}] Raw LLM response:\n{raw[:400]}")

    clips = _parse_response(raw)
    candidates = _validate(clips, float(metadata.get("duration", 0)))

    logger.info(
        f"[{transcript.video_id}] Analysis done via '{provider}' - "
        f"{len(candidates)} valid clips"
    )
    return candidates[:max_clips]
