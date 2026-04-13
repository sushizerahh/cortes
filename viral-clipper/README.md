# ViralClipper

Automatic YouTube Shorts generator. Paste a YouTube URL → get viral-ready 9:16 clips with burned-in karaoke subtitles, powered by Whisper + Claude.

## Features

- **Download** any YouTube video (normal, Shorts, live recordings) via yt-dlp
- **Transcribe** with OpenAI Whisper — word-level timestamps for perfect subtitle sync
- **Analyze** with Claude API — identifies the highest-potential viral moments
- **Clip & reformat** to 1080×1920 (9:16) with smart face-centered crop via ffmpeg
- **Subtitle** with karaoke-style burned-in captions (4 style presets)
- **Learn** from your feedback — the system improves its predictions over time
- **CLI** for power users + **React dashboard** for visual management

---

## Requirements

- Python 3.11+
- Node.js 18+ (for the dashboard)
- ffmpeg installed and on PATH
- Anthropic API key

---

## Installation

### 1. Clone and set up Python environment

```bash
git clone <repo-url>
cd viral-clipper

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. (Optional) Install OpenCV for face-centered crop

```bash
pip install opencv-python-headless
```

---

## CLI Usage

All commands are run from the `backend/` directory with the venv active.

```bash
cd backend

# Process a video — downloads, transcribes, analyzes, clips
python main.py clip "https://youtube.com/watch?v=VIDEO_ID"

# With options
python main.py clip "URL" \
  --style bold \
  --max-clips 5 \
  --min-duration 20 \
  --max-duration 45

# Subtitle styles: default | neon | minimal | bold
python main.py clip "URL" --style neon

# List clips pending feedback
python main.py review --pending

# Rate a clip (use the first 8 chars of clip ID shown in review)
python main.py feedback abc12345 \
  --rating 8 \
  --views 15000 \
  --likes 800 \
  --comments 45 \
  --retention 78.5 \
  --best-moment hook \
  --notes "Great opening line"

# View the learning profile
python main.py learning

# Global statistics
python main.py stats

# Start the web dashboard
python main.py dashboard
```

---

## Web Dashboard

```bash
# Terminal 1 — start API server
cd backend
python main.py dashboard

# Terminal 2 — start React dev server
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

### Dashboard pages

| Page | Description |
|------|-------------|
| **Clip** | Paste URL, configure options, watch real-time progress |
| **Clips** | Browse all generated clips with inline video player |
| **Review** | Rate clips with performance metrics to train the AI |
| **Analytics** | Charts, accuracy stats, and learned rules |
| **History** | All processed videos with expandable clip lists |

---

## Project Structure

```
viral-clipper/
├── backend/
│   ├── main.py          # CLI entry point (Click)
│   ├── config.py        # Global settings from .env
│   ├── database.py      # SQLite operations
│   ├── downloader.py    # yt-dlp wrapper
│   ├── transcriber.py   # Whisper transcription
│   ├── analyzer.py      # Claude API analysis
│   ├── clipper.py       # ffmpeg clipping + vertical reformat
│   ├── subtitler.py     # ASS subtitle generation
│   ├── learning.py      # Feedback-based learning system
│   ├── api_server.py    # FastAPI + WebSocket server
│   └── utils.py         # Shared helpers
├── frontend/
│   └── src/
│       ├── pages/       # Home, Results, Review, Analytics, History
│       ├── components/  # ClipCard, ScoreBadge, CategoryBadge, ProgressBar
│       ├── hooks/       # useWs (WebSocket context)
│       └── api.ts       # Typed API client
├── data/
│   ├── downloads/       # Source videos + audio
│   ├── clips/           # Generated MP4s + thumbnails
│   └── transcripts/     # Cached JSON transcriptions
├── requirements.txt
└── .env.example
```

---

## How the Learning System Works

1. Generate clips from a YouTube video
2. Post the Shorts on YouTube
3. Come back and rate each clip in the **Review** tab:
   - Performance rating (1–10)
   - Actual views / likes / comments
   - Average retention rate
   - Which moment performed best (hook/middle/end)
4. The system computes a **Learning Profile** that identifies:
   - Which categories (humor, shock, insight…) work best for your audience
   - Optimal clip duration range
   - Best hook patterns
5. On the next video, the profile is injected into the Claude prompt — each run is better-calibrated than the last

---

## Subtitle Styles

| Style | Description |
|-------|-------------|
| `default` | White text, black outline, yellow highlight |
| `neon` | Neon green text with glow, magenta highlight |
| `minimal` | Clean white, thin outline, no highlight |
| `bold` | Huge text, thick outline, red highlight (MrBeast style) |

---

## API Reference

The FastAPI server exposes these endpoints (docs at `http://localhost:8000/docs`):

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/process` | Start processing a URL |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/videos` | List processed videos |
| GET | `/api/clips` | List all clips |
| POST | `/api/clips/{id}/feedback` | Submit feedback |
| GET | `/api/clips/{id}/video` | Stream clip video |
| GET | `/api/learning/profile` | Get learning profile |
| GET | `/api/stats` | Global statistics |
| WS | `/ws/progress` | Real-time progress updates |

---

## Tips

- Use **large-v3** Whisper model for best Portuguese transcription accuracy (requires ~10 GB VRAM)
- The `medium` model is a good balance of speed and accuracy
- Face detection requires `opencv-python-headless` — install it for better vertical crops
- Re-analyze old videos after collecting feedback to generate improved clips
