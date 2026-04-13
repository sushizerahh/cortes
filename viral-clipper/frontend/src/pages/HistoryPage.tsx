import { useEffect, useState } from 'react'
import { History, ChevronDown, ChevronUp, RefreshCw, ExternalLink } from 'lucide-react'
import { getVideos, reanalyzeVideo, type Video } from '../api'
import ScoreBadge from '../components/ScoreBadge'
import CategoryBadge from '../components/CategoryBadge'

function formatDuration(secs: number) {
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = Math.floor(secs % 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${s}s`
}

function VideoRow({ video }: { video: Video }) {
  const [open, setOpen] = useState(false)
  const [reanalyzing, setReanalyzing] = useState(false)

  async function handleReanalyze() {
    setReanalyzing(true)
    try {
      await reanalyzeVideo(video.id)
    } catch { /* ignore */ }
    finally { setReanalyzing(false) }
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center gap-4 p-4 text-left hover:bg-white/2 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex-1 min-w-0 space-y-0.5">
          <p className="text-sm font-medium text-white truncate">{video.title}</p>
          <p className="text-xs text-muted">
            {video.channel} · {formatDuration(video.duration)} · {video.language?.toUpperCase() || '?'}
          </p>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-muted">
            {video.clips?.length ?? 0} clips
          </span>
          <span className="text-xs text-muted hidden md:block">
            {new Date(video.processed_at).toLocaleDateString()}
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-border">
          {/* Actions */}
          <div className="flex gap-2 p-4 pb-0">
            <a
              href={video.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-muted hover:text-white transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Open on YouTube
            </a>
            <button
              onClick={handleReanalyze}
              disabled={reanalyzing}
              className="flex items-center gap-1.5 text-xs text-muted hover:text-neon transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${reanalyzing ? 'animate-spin' : ''}`} />
              Re-analyze
            </button>
          </div>

          {/* Clips table */}
          {video.clips && video.clips.length > 0 ? (
            <div className="p-4 space-y-2">
              <p className="text-xs text-muted uppercase tracking-wide">Clips</p>
              <div className="space-y-1">
                {video.clips.map((clip) => (
                  <div key={clip.id} className="flex items-center gap-3 py-2 border-b border-border last:border-0">
                    <ScoreBadge score={clip.viral_score} size="sm" />
                    <p className="flex-1 text-sm text-white truncate">{clip.title}</p>
                    <CategoryBadge category={clip.category} />
                    <span className="text-xs text-muted font-mono">{Math.round(clip.duration)}s</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="p-4 text-sm text-muted">No clips generated yet.</p>
          )}
        </div>
      )}
    </div>
  )
}

export default function HistoryPage() {
  const [videos, setVideos] = useState<Video[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  async function load() {
    setLoading(true)
    try {
      const data = await getVideos(100, 0)
      setVideos(data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const filtered = search.trim()
    ? videos.filter(
        (v) =>
          v.title?.toLowerCase().includes(search.toLowerCase()) ||
          v.channel?.toLowerCase().includes(search.toLowerCase())
      )
    : videos

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <History className="w-5 h-5 text-neon" />
          <h1 className="text-xl font-bold text-white font-mono">History</h1>
          <span className="text-sm text-muted">({videos.length} videos)</span>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-muted hover:text-white transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Search */}
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by title or channel…"
        className="w-full max-w-md bg-card border border-border rounded-xl px-4 py-2.5 text-sm text-white placeholder-muted focus:outline-none focus:border-neon/60 transition-colors"
      />

      {/* List */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl h-16 animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-24">
          <History className="w-12 h-12 text-muted mx-auto mb-3" />
          <p className="text-muted">
            {search ? 'No videos match your search.' : 'No videos processed yet.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((video) => (
            <VideoRow key={video.id} video={video} />
          ))}
        </div>
      )}
    </div>
  )
}
