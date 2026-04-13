import { useEffect, useState } from 'react'
import { TrendingUp, RefreshCw, Brain } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, CartesianGrid, Legend,
} from 'recharts'
import { getLearningProfile, getStats, type LearningProfile, type Stats } from '../api'
import ScoreBadge from '../components/ScoreBadge'

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-1">
      <p className="text-xs text-muted uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-mono font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-muted">{sub}</p>}
    </div>
  )
}

export default function Analytics() {
  const [profile, setProfile] = useState<LearningProfile | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    const [p, s] = await Promise.all([getLearningProfile(), getStats()])
    setProfile(p)
    setStats(s)
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const catData = profile?.category_stats
    ? Object.entries(profile.category_stats).map(([cat, d]) => ({
        name: cat,
        avg_rating: d.avg_rating,
        count: d.count,
        avg_views: Math.round(d.avg_views),
      }))
    : []

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TrendingUp className="w-5 h-5 text-neon" />
          <h1 className="text-xl font-bold text-white font-mono">Analytics</h1>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-muted hover:text-white transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-5 h-24 animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          {/* Stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Videos processed" value={stats?.total_videos ?? 0} />
            <StatCard label="Clips generated" value={stats?.total_clips ?? 0} />
            <StatCard label="Clips rated" value={profile?.total_clips_rated ?? 0} />
            <StatCard
              label="AI accuracy"
              value={`${((profile?.avg_accuracy ?? 0) * 100).toFixed(0)}%`}
              sub="predicted vs actual"
            />
          </div>

          {/* Category performance chart */}
          {catData.length > 0 && (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h2 className="font-mono font-semibold text-white text-sm">Category Performance</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={catData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                  <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} />
                  <YAxis domain={[0, 10]} tick={{ fill: '#6b7280', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{ background: '#1a1a26', border: '1px solid #2a2a3a', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                    itemStyle={{ color: '#00FF88' }}
                  />
                  <Bar dataKey="avg_rating" fill="#00FF88" radius={[4, 4, 0, 0]} name="Avg Rating" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-6">
            {/* Learning profile */}
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-neon" />
                <h2 className="font-mono font-semibold text-white text-sm">Learning Profile</h2>
              </div>

              {profile && profile.total_clips_rated < 5 ? (
                <p className="text-sm text-muted">
                  Rate at least 5 clips to unlock personalized insights.
                  <br />
                  <span className="text-neon font-medium">{profile.total_clips_rated}/5 rated</span>
                </p>
              ) : (
                <div className="space-y-3 text-sm">
                  {profile?.best_performing_categories?.length ? (
                    <div>
                      <p className="text-xs text-muted mb-1">Best categories</p>
                      <div className="flex flex-wrap gap-1">
                        {profile.best_performing_categories.map((cat) => (
                          <span key={cat} className="text-xs px-2 py-0.5 bg-neon/10 text-neon border border-neon/20 rounded capitalize">
                            {cat}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {profile?.optimal_duration_range && (
                    <div>
                      <p className="text-xs text-muted mb-1">Optimal duration</p>
                      <p className="text-neon font-mono font-bold">
                        {profile.optimal_duration_range[0]}–{profile.optimal_duration_range[1]}s
                      </p>
                    </div>
                  )}

                  {profile?.best_hook_types?.length ? (
                    <div>
                      <p className="text-xs text-muted mb-1">Best hook types</p>
                      <ul className="space-y-0.5">
                        {profile.best_hook_types.map((h) => (
                          <li key={h} className="text-xs text-white/80 capitalize">→ {h.replace(/_/g, ' ')}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}
            </div>

            {/* Learned rules */}
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h2 className="font-mono font-semibold text-white text-sm">Learned Rules</h2>
              {profile?.learned_rules?.length ? (
                <ul className="space-y-2">
                  {profile.learned_rules.map((rule, i) => (
                    <li key={i} className="flex gap-2 text-sm">
                      <span className="text-neon mt-0.5 flex-shrink-0">→</span>
                      <span className="text-white/80">{rule}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted">No rules learned yet. Keep rating clips!</p>
              )}
            </div>
          </div>

          {/* Top clips */}
          {stats?.top_clips?.length ? (
            <div className="bg-card border border-border rounded-xl p-6 space-y-4">
              <h2 className="font-mono font-semibold text-white text-sm">Top 5 Clips by Views</h2>
              <div className="space-y-2">
                {stats.top_clips.map((clip, i) => (
                  <div key={clip.id} className="flex items-center gap-4 py-2 border-b border-border last:border-0">
                    <span className="text-muted font-mono text-sm w-6">#{i + 1}</span>
                    <p className="flex-1 text-sm text-white truncate">{clip.title}</p>
                    <ScoreBadge score={clip.viral_score} size="sm" />
                    <span className="text-sm text-muted font-mono">{(clip.views ?? 0).toLocaleString()} views</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
