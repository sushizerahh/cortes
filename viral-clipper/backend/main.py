"""
ViralClipper CLI — entry point for all command-line operations.
Usage: python main.py [COMMAND] [OPTIONS]
"""

import logging
import sys
import uuid
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich import print as rprint

from config import (
    CLIP_MAX_DURATION,
    CLIP_MIN_DURATION,
    DEFAULT_SUBTITLE_STYLE,
    LOG_FILE,
    LOG_LEVEL,
    MAX_CLIPS_PER_VIDEO,
)
from database import (
    get_clip,
    get_stats,
    init_db,
    insert_clip,
    list_clips,
    list_clips_without_feedback,
    list_videos,
    update_clip_paths,
)
from utils import format_duration, setup_logging

console = Console()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def _score_badge(score: float) -> str:
    if score >= 8:
        return f"[bold green]{score:.1f}[/bold green]"
    if score >= 6:
        return f"[bold yellow]{score:.1f}[/bold yellow]"
    return f"[bold red]{score:.1f}[/bold red]"


# ─── Main group ───────────────────────────────────────────────────────────────

@click.group()
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging.")
def cli(debug: bool) -> None:
    """ViralClipper — Automatic YouTube Shorts generator."""
    level = "DEBUG" if debug else LOG_LEVEL
    setup_logging(level, LOG_FILE)
    init_db()


# ─── clip command ─────────────────────────────────────────────────────────────

@cli.command()
@click.argument("url")
@click.option("--style", default=DEFAULT_SUBTITLE_STYLE,
              type=click.Choice(["default", "neon", "minimal", "bold"]),
              help="Subtitle style.", show_default=True)
@click.option("--max-clips", default=MAX_CLIPS_PER_VIDEO, show_default=True,
              help="Maximum number of clips to generate.")
@click.option("--min-duration", default=CLIP_MIN_DURATION, show_default=True,
              help="Minimum clip duration in seconds.")
@click.option("--max-duration", default=CLIP_MAX_DURATION, show_default=True,
              help="Maximum clip duration in seconds.")
@click.option("--force", is_flag=True, default=False,
              help="Re-download and re-process even if cached.")
@click.option("--no-subtitles", is_flag=True, default=False,
              help="Skip subtitle generation.")
def clip(
    url: str,
    style: str,
    max_clips: int,
    min_duration: int,
    max_duration: int,
    force: bool,
    no_subtitles: bool,
) -> None:
    """Download a YouTube video and generate viral Shorts clips."""
    from downloader import download, DownloadError
    from transcriber import transcribe, TranscriptionError
    from analyzer import analyze, AnalysisError
    from clipper import process_clip, ClipError
    from subtitler import generate_for_clip
    from learning import get_profile_for_prompt
    from transcriber import get_words_in_range

    console.print(Panel.fit(
        f"[bold green]ViralClipper[/bold green] — processing URL\n[dim]{url}[/dim]",
        border_style="green",
    ))

    # ── Step 1: Download ──────────────────────────────────────────────────────
    with _progress() as prog:
        task = prog.add_task("Downloading video …", total=None)
        try:
            dl = download(url, force=force)
            prog.update(task, description="[green]Download complete[/green]", completed=1, total=1)
        except DownloadError as e:
            console.print(f"[bold red]Download failed:[/bold red] {e}")
            sys.exit(1)

    console.print(f"  [dim]Video:[/dim] {dl.title}")
    console.print(f"  [dim]Channel:[/dim] {dl.channel}")
    console.print(f"  [dim]Duration:[/dim] {format_duration(dl.duration)}")

    # Persist video record
    from database import upsert_video
    upsert_video(
        video_id=dl.video_id,
        url=url,
        title=dl.title,
        channel=dl.channel,
        duration=dl.duration,
        language="",
        metadata=dl.metadata,
    )

    # ── Step 2: Transcribe ────────────────────────────────────────────────────
    with _progress() as prog:
        task = prog.add_task("Transcribing audio (may take a few minutes) …", total=None)
        try:
            transcript = transcribe(dl.audio_path, dl.video_id, force=force)
            prog.update(task, description="[green]Transcription complete[/green]", completed=1, total=1)
        except TranscriptionError as e:
            console.print(f"[bold red]Transcription failed:[/bold red] {e}")
            sys.exit(1)

    # Update language
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            "UPDATE videos SET language = ? WHERE id = ?",
            (transcript.language, dl.video_id),
        )
    console.print(f"  [dim]Language:[/dim] {transcript.language or 'unknown'}")
    console.print(f"  [dim]Segments:[/dim] {len(transcript.segments)}")

    # ── Step 3: Analyze ───────────────────────────────────────────────────────
    with _progress() as prog:
        task = prog.add_task("Analyzing viral moments with Claude …", total=None)
        learning_profile = get_profile_for_prompt()
        try:
            candidates = analyze(
                transcript=transcript,
                metadata=dl.metadata,
                learning_profile=learning_profile,
                max_clips=max_clips,
            )
            prog.update(task, description="[green]Analysis complete[/green]", completed=1, total=1)
        except AnalysisError as e:
            console.print(f"[bold red]Analysis failed:[/bold red] {e}")
            sys.exit(1)

    console.print(f"  [dim]Candidates found:[/dim] {len(candidates)}")

    # ── Step 4: Clip + Subtitle ───────────────────────────────────────────────
    generated = []
    with _progress() as prog:
        task = prog.add_task("Generating clips …", total=len(candidates))
        for i, candidate in enumerate(candidates):
            prog.update(task, description=f"Clipping [{i+1}/{len(candidates)}]: {candidate.title[:40]}")

            clip_id = str(uuid.uuid4())

            # Generate subtitles
            ass_file = None
            if not no_subtitles:
                clip_words = get_words_in_range(transcript, candidate.start_time, candidate.end_time)
                ass_file = generate_for_clip(
                    all_words=clip_words,
                    clip_start=candidate.start_time,
                    clip_end=candidate.end_time,
                    video_id=dl.video_id,
                    clip_index=i,
                    style_name=style,
                )

            # Insert placeholder record
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
                "subtitle_style": style,
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
                generated.append((clip_id, candidate, clip_path))
            except ClipError as e:
                console.print(f"  [yellow]Warning:[/yellow] Clip {i+1} failed: {e}")

            prog.advance(task)

    # ── Results Table ─────────────────────────────────────────────────────────
    table = Table(title="Generated Clips", show_lines=True, border_style="green")
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=30)
    table.add_column("Duration", justify="right")
    table.add_column("Score", justify="center")
    table.add_column("Category")
    table.add_column("File", style="dim")

    for i, (cid, cand, path) in enumerate(generated, 1):
        table.add_row(
            str(i),
            cand.title,
            format_duration(cand.duration),
            _score_badge(cand.viral_score),
            cand.category,
            path.name,
        )

    console.print(table)
    console.print(f"\n[bold green]✓[/bold green] {len(generated)} clips saved to [dim]data/clips/[/dim]")


# ─── review command ───────────────────────────────────────────────────────────

@cli.command()
@click.option("--pending", is_flag=True, default=False, help="Show only unreviewed clips.")
def review(pending: bool) -> None:
    """List clips and review status."""
    if pending:
        clips = list_clips_without_feedback()
        console.print(f"\n[bold yellow]{len(clips)} clips awaiting feedback[/bold yellow]\n")
    else:
        clips = list_clips()

    if not clips:
        console.print("[dim]No clips found.[/dim]")
        return

    table = Table(show_lines=True)
    table.add_column("ID", style="dim", width=8)
    table.add_column("Title", min_width=30)
    table.add_column("Duration", justify="right")
    table.add_column("Score", justify="center")
    table.add_column("Category")
    table.add_column("Created", style="dim")

    for c in clips:
        short_id = c["id"][:8]
        table.add_row(
            short_id,
            c.get("title", "?"),
            format_duration(c.get("duration") or 0),
            _score_badge(c.get("viral_score") or 0),
            c.get("category", "?"),
            str(c.get("created_at", ""))[:16],
        )
    console.print(table)
    console.print("\n[dim]Use 'python main.py feedback CLIP_ID ...' to rate a clip.[/dim]")


# ─── feedback command ─────────────────────────────────────────────────────────

@cli.command()
@click.argument("clip_id")
@click.option("--rating", type=click.IntRange(1, 10), required=True, help="Performance rating 1-10.")
@click.option("--views", type=int, default=0, help="Number of views the Short received.")
@click.option("--likes", type=int, default=0, help="Number of likes.")
@click.option("--comments", type=int, default=0, help="Number of comments.")
@click.option("--retention", type=float, default=0.0, help="Average retention rate (%).")
@click.option("--best-moment", type=click.Choice(["hook", "middle", "end"]),
              default=None, help="Which part performed best.")
@click.option("--notes", default="", help="Free-form notes.")
def feedback(
    clip_id: str,
    rating: int,
    views: int,
    likes: int,
    comments: int,
    retention: float,
    best_moment: str,
    notes: str,
) -> None:
    """Record performance feedback for a clip."""
    from learning import record_feedback

    # Accept short IDs — look up full ID
    all_clips = list_clips()
    matched = [c for c in all_clips if c["id"].startswith(clip_id)]
    if not matched:
        console.print(f"[bold red]Error:[/bold red] No clip found with ID starting with {clip_id!r}")
        sys.exit(1)
    if len(matched) > 1:
        console.print(f"[bold red]Error:[/bold red] Multiple clips match {clip_id!r} — be more specific")
        sys.exit(1)

    full_id = matched[0]["id"]
    fb = {
        "clip_id": full_id,
        "performance_rating": rating,
        "views": views,
        "likes": likes,
        "comments": comments,
        "retention_rate": retention,
        "best_moment": best_moment,
        "notes": notes,
    }

    profile = record_feedback(fb)
    console.print(f"[bold green]✓[/bold green] Feedback recorded for clip [dim]{full_id[:8]}[/dim]")
    console.print(
        f"  Learning profile updated — "
        f"{profile['total_clips_rated']} clips rated, "
        f"accuracy={profile['avg_accuracy']:.1%}"
    )


# ─── learning command ─────────────────────────────────────────────────────────

@cli.command("learning")
def learning_cmd() -> None:
    """Display the current learning profile."""
    from learning import compute_learning_profile
    from rich.pretty import Pretty

    profile = compute_learning_profile()

    console.print(Panel.fit(
        f"[bold]Learning Profile[/bold]\n"
        f"Total clips rated: [bold]{profile['total_clips_rated']}[/bold]\n"
        f"Prediction accuracy: [bold]{profile['avg_accuracy']:.1%}[/bold]",
        border_style="cyan",
    ))

    if profile.get("best_performing_categories"):
        console.print("\n[bold cyan]Best Categories:[/bold cyan]")
        for cat in profile["best_performing_categories"]:
            console.print(f"  • {cat}")

    if profile.get("optimal_duration_range"):
        low, high = profile["optimal_duration_range"]
        console.print(f"\n[bold cyan]Optimal Duration:[/bold cyan] {low}–{high}s")

    if profile.get("learned_rules"):
        console.print("\n[bold cyan]Learned Rules:[/bold cyan]")
        for rule in profile["learned_rules"]:
            console.print(f"  [dim]→[/dim] {rule}")


# ─── stats command ────────────────────────────────────────────────────────────

@cli.command()
def stats() -> None:
    """Show overall system statistics."""
    s = get_stats()
    console.print(Panel.fit(
        f"[bold]ViralClipper Stats[/bold]\n\n"
        f"Videos processed:   [bold]{s['total_videos']}[/bold]\n"
        f"Clips generated:    [bold]{s['total_clips']}[/bold]\n"
        f"Feedback entries:   [bold]{s['total_feedback']}[/bold]\n"
        f"Avg viral score:    [bold]{s['avg_viral_score']:.1f}/10[/bold]\n"
        f"Awaiting feedback:  [bold yellow]{s['pending_feedback']}[/bold yellow]",
        border_style="blue",
    ))

    if s["top_clips"]:
        table = Table(title="Top Clips by Views", show_lines=True)
        table.add_column("Title")
        table.add_column("Viral Score", justify="center")
        table.add_column("Views", justify="right")
        table.add_column("Rating", justify="center")
        for c in s["top_clips"]:
            table.add_row(
                c.get("title", "?")[:40],
                _score_badge(c.get("viral_score") or 0),
                f"{c.get('views', 0):,}",
                str(c.get("performance_rating", "?")),
            )
        console.print(table)


# ─── dashboard command ────────────────────────────────────────────────────────

@cli.command()
@click.option("--port", default=8000, show_default=True, help="API server port.")
@click.option("--host", default="127.0.0.1", show_default=True, help="API server host.")
def dashboard(port: int, host: str) -> None:
    """Start the ViralClipper web dashboard (API + frontend instructions)."""
    import uvicorn

    console.print(Panel.fit(
        f"[bold green]Starting ViralClipper Dashboard[/bold green]\n\n"
        f"API server: [bold]http://{host}:{port}[/bold]\n"
        f"API docs:   [bold]http://{host}:{port}/docs[/bold]\n\n"
        f"[dim]Start the React frontend separately:\n"
        f"  cd frontend && npm install && npm run dev[/dim]",
        border_style="green",
    ))

    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    cli()
