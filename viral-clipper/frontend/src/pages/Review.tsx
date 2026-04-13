import { useEffect, useState } from 'react'
import { MessageSquare, Check, ChevronLeft, ChevronRight } from 'lucide-react'
import { getPendingFeedback, submitFeedback, clipVideoUrl, type Clip, type Feedback } from '../api'
import ScoreBadge from '../components/ScoreBadge'
import CategoryBadge from '../components/CategoryBadge'

const EMOJIS = ['', '😞', '😕', '😐', '🙂', '😊', '😄', '🔥', '🚀', '💥', '🌟']

const EMPTY_FEEDBACK: Feedback = {
  performance_rating: 7,
  views: 0,
  likes: 0,
  comments: 0,
  retention_rate: 0,
  best_moment: undefined,
  notes: '',
}

export default function Review() {
  const [clips, setClips] = useState<Clip[]>([])
  const [idx, setIdx] = useState(0)
  const [feedback, setFeedback] = useState<Feedback>(EMPTY_FEEDBACK)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getPendingFeedback().then((data) => {
      setClips(data)
      setLoading(false)
    })
  }, [])

  const clip = clips[idx]

  function prev() { setIdx((i) => Math.max(0, i - 1)); setSaved(false); setFeedback(EMPTY_FEEDBACK) }
  function next() { setIdx((i) => Math.min(clips.length - 1, i + 1)); setSaved(false); setFeedback(EMPTY_FEEDBACK) }

  async function save() {
    if (!clip) return
    setSaving(true)
    try {
      await submitFeedback(clip.id, feedback)
      setSaved(true)
      // Remove from pending list after a moment
      setTimeout(() => {
        setClips((prev) => prev.filter((_, i) => i !== idx))
        setIdx((i) => Math.min(i, clips.length - 2))
        setSaved(false)
        setFeedback(EMPTY_FEEDBACK)
      }, 800)
    } catch (e) {
      console.error(e)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-96">
        <div className="text-muted animate-pulse">Loading…</div>
      </div>
    )
  }

  if (clips.length === 0) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-96 space-y-3 text-center">
        <Check className="w-12 h-12 text-neon" />
        <p className="text-white font-medium">All caught up!</p>
        <p className="text-sm text-muted">No clips are waiting for feedback right now.</p>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <MessageSquare className="w-5 h-5 text-neon" />
          <h1 className="text-xl font-bold text-white font-mono">Review</h1>
        </div>
        <span className="text-sm text-muted">
          {idx + 1} / {clips.length} pending
        </span>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Video player */}
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="aspect-[9/16] bg-black flex items-center justify-center" style={{ maxHeight: 420 }}>
              <video
                key={clip.id}
                src={clipVideoUrl(clip.id)}
                controls
                className="h-full w-full object-contain"
              />
            </div>
            <div className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-white text-sm">{clip.title}</h2>
                <ScoreBadge score={clip.viral_score} size="sm" />
              </div>
              <div className="flex items-center gap-2">
                <CategoryBadge category={clip.category} />
                <span className="text-xs text-muted">{Math.round(clip.duration)}s</span>
              </div>
              {clip.reasoning && (
                <p className="text-xs text-muted">{clip.reasoning}</p>
              )}
            </div>
          </div>

          {/* Navigation */}
          <div className="flex gap-2">
            <button
              onClick={prev}
              disabled={idx === 0}
              className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-card border border-border text-muted hover:text-white disabled:opacity-30 transition-colors text-sm"
            >
              <ChevronLeft className="w-4 h-4" /> Prev
            </button>
            <button
              onClick={next}
              disabled={idx >= clips.length - 1}
              className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-card border border-border text-muted hover:text-white disabled:opacity-30 transition-colors text-sm"
            >
              Next <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Feedback form */}
        <div className="bg-card border border-border rounded-xl p-6 space-y-5">
          <h3 className="font-mono font-semibold text-white">Rate this clip</h3>

          {/* Rating slider */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm text-muted">Performance rating</label>
              <span className="text-2xl">{EMOJIS[feedback.performance_rating]}</span>
            </div>
            <input
              type="range" min={1} max={10} value={feedback.performance_rating}
              onChange={(e) => setFeedback({ ...feedback, performance_rating: Number(e.target.value) })}
              className="w-full accent-neon"
            />
            <div className="flex justify-between text-xs text-muted">
              <span>1 — Flop</span>
              <span className="font-mono text-neon font-bold text-base">{feedback.performance_rating}/10</span>
              <span>10 — Viral</span>
            </div>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-2 gap-3">
            {([
              ['Views', 'views', 0],
              ['Likes', 'likes', 0],
              ['Comments', 'comments', 0],
              ['Retention %', 'retention_rate', 0],
            ] as [string, keyof Feedback, number][]).map(([label, key, min]) => (
              <label key={key} className="space-y-1">
                <span className="text-xs text-muted">{label}</span>
                <input
                  type="number" min={min} value={(feedback[key] as number) ?? 0}
                  onChange={(e) =>
                    setFeedback({ ...feedback, [key]: Number(e.target.value) })
                  }
                  className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-neon/60"
                />
              </label>
            ))}
          </div>

          {/* Best moment */}
          <div className="space-y-1">
            <label className="text-xs text-muted">Best performing moment</label>
            <div className="flex gap-2">
              {(['hook', 'middle', 'end'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setFeedback({ ...feedback, best_moment: m })}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-all capitalize ${
                    feedback.best_moment === m
                      ? 'bg-neon/10 text-neon border-neon/30'
                      : 'bg-bg text-muted border-border hover:text-white'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div className="space-y-1">
            <label className="text-xs text-muted">Notes (optional)</label>
            <textarea
              value={feedback.notes}
              onChange={(e) => setFeedback({ ...feedback, notes: e.target.value })}
              placeholder="What worked? What didn't?"
              rows={3}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-muted focus:outline-none focus:border-neon/60 resize-none"
            />
          </div>

          {/* Save */}
          <button
            onClick={save}
            disabled={saving || saved}
            className={`w-full py-2.5 rounded-xl font-semibold text-sm transition-all ${
              saved
                ? 'bg-neon/20 text-neon border border-neon/30'
                : 'bg-neon text-black hover:bg-neon-dim active:scale-[0.99] disabled:opacity-50'
            }`}
          >
            {saved ? '✓ Saved!' : saving ? 'Saving…' : 'Save Feedback'}
          </button>
        </div>
      </div>
    </div>
  )
}
