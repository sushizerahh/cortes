"""
FastAPI server — backend for the ViralClipper web dashboard.
Provides REST endpoints + WebSocket for real-time progress.
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from config import (
    CLIPS_DIR,
    CLIP_MAX_DURATION,
    CLIP_MIN_DURATION,
    CORS_ORIGINS,
    DEFAULT_SUBTITLE_STYLE,
    MAX_CLIPS_PER_VIDEO,
)
from database import (
    get_clip,
    get_learning_profile,
    get_stats,
    init_db,
    insert_clip,
    list_clips,
    list_clips_without_feedback,
    list_videos,
    get_video,
    update_clip_paths,
    upsert_video,
)
from utils import setup_logging

logger = logging.getLogger(__name__)
setup_logging()
init_db()

app = FastAPI(
    title="ViralClipper API",
    description="Automatic YouTube Shorts generator backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Job State ────────────────────────────────────────────────────────────────

_jobs: dict[str, dict] = {}  # job_id → {status, progress, steps, error, result}
_ws_clients: set[WebSocket] = set()


async def _broadcast(message: dict) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.add(ws)
    _ws_clients.difference_update(disconnected)


def _update_job(job_id: str, **kwargs: Any) -> None:
    """Update job state and schedule a broadcast."""
    _jobs[job_id].update(kwargs)
    asyncio.create_task(_broadcast({"type": "job_update", "job_id": job_id, **kwargs}))


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    url: str
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE
    max_clips: int = MAX_CLIPS_PER_VIDEO
    min_duration: int = CLIP_MIN_DURATION
    max_duration: int = CLIP_MAX_DURATION
    no_subtitles: bool = False

    @field_validator("subtitle_style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        valid = {"default", "neon", "minimal", "bold"}
        if v not in valid:
            raise ValueError(f"subtitle_style must be one of {valid}")
        return v


class FeedbackRequest(BaseModel):
    performance_rating: int
    views: int = 0
    likes: int = 0
    comments: int = 0
    retention_rate: float = 0.0
    best_moment: Optional[str] = None
    notes: str = ""

    @field_validator("performance_rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("performance_rating must be between 1 and 10")
        return v


# ─── Background Processing ────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, req: ProcessRequest) -> None:
    """Full processing pipeline run in a background task."""
    from downloader import download, DownloadError
    from transcriber import transcribe, TranscriptionError, get_words_in_range
    from analyzer import analyze, AnalysisError
    from clipper import process_clip, ClipError
    from subtitler import generate_for_clip
    from learning import get_profile_for_prompt

    def step(name: str, progress: int) -> None:
        _jobs[job_id]["step"] = name
        _jobs[job_id]["progress"] = progress
        asyncio.create_task(_broadcast({
            "type": "progress",
            "job_id": job_id,
            "step": name,
            "progress": progress,
        }))

    try:
        _jobs[job_id]["status"] = "running"

        # 1. Download
        step("downloading", 10)
        dl = download(req.url)
        upsert_video(
            video_id=dl.video_id,
            url=req.url,
            title=dl.title,
            channel=dl.channel,
            duration=dl.duration,
            language="",
            metadata=dl.metadata,
        )

        # 2. Transcribe
        step("transcribing", 30)
        transcript = transcribe(dl.audio_path, dl.video_id)
        from database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE videos SET language = ? WHERE id = ?",
                (transcript.language, dl.video_id),
            )

        # 3. Analyze
        step("analyzing", 55)
        learning_profile = get_profile_for_prompt()
        candidates = analyze(
            transcript=transcript,
            metadata=dl.metadata,
            learning_profile=learning_profile,
            max_clips=req.max_clips,
        )

        # 4. Clip + subtitle
        generated_clips = []
        total = len(candidates)
        for i, candidate in enumerate(candidates):
            step(f"clipping {i+1}/{total}", 60 + int(35 * (i / max(total, 1))))
            clip_id = str(uuid.uuid4())

            ass_file = None
            if not req.no_subtitles:
                clip_words = get_words_in_range(transcript, candidate.start_time, candidate.end_time)
                ass_file = generate_for_clip(
                    all_words=clip_words,
                    clip_start=candidate.start_time,
                    clip_end=candidate.end_time,
                    video_id=dl.video_id,
                    clip_index=i,
                    style_name=req.subtitle_style,
                )

            clip_record = {
                "id": clip_id,
                "video_id": dl.video_id,
                "title": candidate.title,
                "start_time": candidate.start_time,
                "end_time": candidate.end_time,
                "duration": candidate.duration,
                "viral_score": candidate.viral_score,
                "category": candidate.category,
                "hook": candidate.hook,
                "reasoning": candidate.reasoning,
                "suggested_caption": candidate.suggested_caption,
                "subtitle_style": req.subtitle_style,
            }
            insert_clip(clip_record)

            try:
                clip_path, thumb_path = process_clip(
                    video_path=dl.video_path,
                    video_id=dl.video_id,
                    clip_index=i,
                    title=candidate.title,
                    start_time=candidate.start_time,
                    end_time=candidate.end_time,
                    ass_file=ass_file,
                )
                update_clip_paths(clip_id, str(clip_path), str(thumb_path))
                clip_record["file_path"] = str(clip_path)
                clip_record["thumbnail_path"] = str(thumb_path)
            except ClipError as e:
                logger.warning(f"Clip {i+1} rendering failed: {e}")

            generated_clips.append(clip_record)

        step("done", 100)
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result"] = {
            "video_id": dl.video_id,
            "clips": generated_clips,
        }
        await _broadcast({"type": "done", "job_id": job_id, "video_id": dl.video_id})

    except Exception as e:
        logger.exception(f"Pipeline failed for job {job_id}")
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)
        await _broadcast({"type": "error", "job_id": job_id, "error": str(e)})


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.post("/api/process")
async def process_video(req: ProcessRequest, background_tasks: BackgroundTasks) -> dict:
    """Kick off the full clip-generation pipeline for a YouTube URL."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "queued",
        "progress": 0,
        "url": req.url,
        "error": None,
        "result": None,
    }
    background_tasks.add_task(_run_pipeline, job_id, req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs")
async def list_jobs() -> list[dict]:
    """List all processing jobs and their current status."""
    return list(_jobs.values())


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/api/videos")
async def get_videos(limit: int = 50, offset: int = 0) -> list[dict]:
    return list_videos(limit=limit, offset=offset)


@app.get("/api/videos/{video_id}")
async def get_video_detail(video_id: str) -> dict:
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    clips = list_clips(video_id=video_id)
    video["clips"] = clips
    return video


@app.get("/api/clips")
async def get_clips(limit: int = 100) -> list[dict]:
    return list_clips(limit=limit)


@app.get("/api/clips/pending-feedback")
async def get_pending_feedback_clips() -> list[dict]:
    return list_clips_without_feedback()


@app.get("/api/clips/{clip_id}")
async def get_clip_detail(clip_id: str) -> dict:
    c = get_clip(clip_id)
    if not c:
        raise HTTPException(status_code=404, detail="Clip not found")
    return c


@app.post("/api/clips/{clip_id}/feedback")
async def submit_feedback(clip_id: str, req: FeedbackRequest) -> dict:
    """Record user feedback for a clip and update the learning profile."""
    from learning import record_feedback

    c = get_clip(clip_id)
    if not c:
        raise HTTPException(status_code=404, detail="Clip not found")

    fb = {
        "clip_id": clip_id,
        "performance_rating": req.performance_rating,
        "views": req.views,
        "likes": req.likes,
        "comments": req.comments,
        "retention_rate": req.retention_rate,
        "best_moment": req.best_moment,
        "notes": req.notes,
    }
    profile = record_feedback(fb)
    return {"status": "ok", "learning_profile": profile}


@app.get("/api/clips/{clip_id}/video")
async def stream_clip(clip_id: str) -> FileResponse:
    """Stream a clip video file."""
    c = get_clip(clip_id)
    if not c or not c.get("file_path"):
        raise HTTPException(status_code=404, detail="Clip file not found")
    path = Path(c["file_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Clip file missing from disk")
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/api/clips/{clip_id}/thumbnail")
async def get_thumbnail(clip_id: str) -> FileResponse:
    """Return the thumbnail image for a clip."""
    c = get_clip(clip_id)
    if not c or not c.get("thumbnail_path"):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    path = Path(c["thumbnail_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing from disk")
    return FileResponse(str(path), media_type="image/jpeg")


@app.get("/api/learning/profile")
async def learning_profile() -> dict:
    """Return the current learning profile."""
    from learning import compute_learning_profile
    return compute_learning_profile()


@app.get("/api/stats")
async def global_stats() -> dict:
    return get_stats()


@app.post("/api/reanalyze/{video_id}")
async def reanalyze(video_id: str, background_tasks: BackgroundTasks) -> dict:
    """Re-run analysis on a previously processed video using the updated learning profile."""
    video = get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    req = ProcessRequest(url=video["url"])
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "queued",
        "progress": 0,
        "url": video["url"],
        "error": None,
        "result": None,
    }
    background_tasks.add_task(_run_pipeline, job_id, req)
    return {"job_id": job_id, "status": "queued"}


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time job progress updates."""
    await websocket.accept()
    _ws_clients.add(websocket)
    # Send current jobs snapshot on connect
    await websocket.send_json({"type": "snapshot", "jobs": list(_jobs.values())})
    try:
        while True:
            # Keep connection alive — client can send pings
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
