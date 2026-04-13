import { useEffect, useState } from 'react'
import { LayoutGrid, RefreshCw } from 'lucide-react'
import { getClips, type Clip } from '../api'
import ClipCard from '../components/ClipCard'
import CategoryBadge from '../components/CategoryBadge'

const CATEGORIES = ['all', 'humor', 'shock', 'insight', 'drama', 'motivation', 'controversy']

export default function Results() {
  const [clips, setClips] = useState<Clip[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  async function load() {
    setLoading(true)
    try {
      const data = await getClips(200)
      setClips(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const visible = filter === 'all' ? clips : clips.filter((c) => c.category === filter)

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <LayoutGrid className="w-5 h-5 text-neon" />
          <h1 className="text-xl font-bold text-white font-mono">Clips</h1>
          <span className="text-sm text-muted">({clips.length} total)</span>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-muted hover:text-white transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Category filter */}
      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              filter === cat
                ? 'bg-neon/10 text-neon border-neon/30'
                : 'bg-card text-muted border-border hover:text-white'
            }`}
          >
            {cat === 'all' ? 'All' : <CategoryBadge category={cat} />}
          </button>
        ))}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl overflow-hidden animate-pulse">
              <div className="aspect-[9/16] bg-border" style={{ maxHeight: 280 }} />
              <div className="p-3 space-y-2">
                <div className="h-4 bg-border rounded w-3/4" />
                <div className="h-3 bg-border rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : visible.length === 0 ? (
        <div className="text-center py-24 space-y-3">
          <LayoutGrid className="w-12 h-12 text-muted mx-auto" />
          <p className="text-muted">No clips yet. Go to the Home tab and process a YouTube URL!</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {visible.map((clip) => (
            <ClipCard key={clip.id} clip={clip} />
          ))}
        </div>
      )}
    </div>
  )
}
