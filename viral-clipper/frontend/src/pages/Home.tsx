import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Scissors, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { processVideo, type SubtitleStyle } from '../api'
import { useWs } from '../hooks/useWs'
import ProgressBar from '../components/ProgressBar'

export default function Home() {
  const [url, setUrl] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [style, setStyle] = useState<SubtitleStyle>('default')
  const [maxClips, setMaxClips] = useState(8)
  const [minDur, setMinDur] = useState(15)
  const [maxDur, setMaxDur] = useState(59)
  const [noSubs, setNoSubs] = useState(false)
  const { jobs } = useWs()
  const navigate = useNavigate()

  const job = jobId ? jobs[jobId] : null

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setError('')
    setLoading(true)
    try {
      const res = await processVideo({
        url: url.trim(),
        subtitle_style: style,
        max_clips: maxClips,
        min_duration: minDur,
        max_duration: maxDur,
        no_subtitles: noSubs,
      })
      setJobId(res.job_id)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const isDone = job?.status === 'done'
  const isError = job?.status === 'error'

  if (isDone) {
    setTimeout(() => navigate('/results'), 1500)
  }

  return (
    <div className="min-h-full flex flex-col items-center justify-center p-6 md:p-12">
      <div className="w-full max-w-2xl space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="flex items-center justify-center gap-3">
            <Scissors className="w-8 h-8 text-neon" />
            <h1 className="font-mono text-3xl font-bold text-white">ViralClipper</h1>
          </div>
          <p className="text-muted">
            Paste a YouTube URL and get viral Shorts clips in minutes
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=..."
              required
              disabled={loading || !!job}
              className={clsx(
                'flex-1 bg-card border rounded-xl px-4 py-3 text-white placeholder-muted',
                'focus:outline-none focus:border-neon/60 transition-colors',
                'disabled:opacity-50',
                error ? 'border-red-500' : 'border-border'
              )}
            />
            <button
              type="submit"
              disabled={loading || !!job || !url.trim()}
              className={clsx(
                'px-6 py-3 rounded-xl font-semibold transition-all duration-200',
                'bg-neon text-black hover:bg-neon-dim active:scale-95',
                'disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2'
              )}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Scissors className="w-4 h-4" />}
              Clip
            </button>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {/* Advanced options */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setAdvanced(!advanced)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm text-muted hover:text-white transition-colors"
            >
              Advanced options
              {advanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {advanced && (
              <div className="px-4 pb-4 grid grid-cols-2 gap-4 border-t border-border pt-4">
                <label className="space-y-1">
                  <span className="text-xs text-muted">Subtitle style</span>
                  <select
                    value={style}
                    onChange={(e) => setStyle(e.target.value as SubtitleStyle)}
                    className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-neon/60"
                  >
                    {['default', 'neon', 'minimal', 'bold'].map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>

                <label className="space-y-1">
                  <span className="text-xs text-muted">Max clips</span>
                  <input
                    type="number" min={1} max={20} value={maxClips}
                    onChange={(e) => setMaxClips(Number(e.target.value))}
                    className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-neon/60"
                  />
                </label>

                <label className="space-y-1">
                  <span className="text-xs text-muted">Min duration (s)</span>
                  <input
                    type="number" min={5} max={30} value={minDur}
                    onChange={(e) => setMinDur(Number(e.target.value))}
                    className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-neon/60"
                  />
                </label>

                <label className="space-y-1">
                  <span className="text-xs text-muted">Max duration (s)</span>
                  <input
                    type="number" min={15} max={60} value={maxDur}
                    onChange={(e) => setMaxDur(Number(e.target.value))}
                    className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-neon/60"
                  />
                </label>

                <label className="col-span-2 flex items-center gap-2 text-sm text-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={noSubs}
                    onChange={(e) => setNoSubs(e.target.checked)}
                    className="accent-neon"
                  />
                  Skip subtitle generation
                </label>
              </div>
            )}
          </div>
        </form>

        {/* Job progress */}
        {job && (
          <div className={clsx(
            'bg-card border rounded-xl p-6 space-y-4',
            isError ? 'border-red-500/30' : isDone ? 'border-neon/30' : 'border-border'
          )}>
            {isError ? (
              <div className="text-center space-y-2">
                <p className="text-red-400 font-medium">Processing failed</p>
                <p className="text-sm text-muted">{job.error}</p>
                <button
                  onClick={() => { setJobId(null); setUrl('') }}
                  className="text-xs text-muted hover:text-white underline"
                >
                  Try again
                </button>
              </div>
            ) : isDone ? (
              <div className="text-center space-y-2">
                <p className="text-neon font-bold text-lg">Done! Redirecting to clips…</p>
              </div>
            ) : (
              <ProgressBar
                step={job.step}
                progress={job.progress}
                status={job.status}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
