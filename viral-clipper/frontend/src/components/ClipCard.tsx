import { useState } from 'react'
import { Play, Download, X } from 'lucide-react'
import ScoreBadge from './ScoreBadge'
import CategoryBadge from './CategoryBadge'
import { clipVideoUrl, clipThumbnailUrl, type Clip } from '../api'

interface Props {
  clip: Clip
}

function formatDuration(secs: number) {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function ClipCard({ clip }: Props) {
  const [playing, setPlaying] = useState(false)

  return (
    <>
      <div className="bg-card border border-border rounded-xl overflow-hidden hover:border-neon/30 transition-all duration-200 group">
        {/* Thumbnail */}
        <div
          className="relative aspect-[9/16] bg-black cursor-pointer overflow-hidden"
          style={{ maxHeight: 280 }}
          onClick={() => setPlaying(true)}
        >
          <img
            src={clipThumbnailUrl(clip.id)}
            alt={clip.title}
            className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
            onError={(e) => {
              ;(e.target as HTMLImageElement).style.display = 'none'
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-12 h-12 rounded-full bg-black/60 border border-white/20 flex items-center justify-center group-hover:bg-neon/20 group-hover:border-neon/50 transition-all">
              <Play className="w-5 h-5 text-white ml-0.5" fill="currentColor" />
            </div>
          </div>
          <div className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded font-mono">
            {formatDuration(clip.duration)}
          </div>
        </div>

        {/* Info */}
        <div className="p-3 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-medium text-white leading-snug line-clamp-2 flex-1">
              {clip.title}
            </p>
            <ScoreBadge score={clip.viral_score} size="sm" />
          </div>

          <CategoryBadge category={clip.category} />

          {clip.hook && (
            <p className="text-xs text-muted italic line-clamp-1">"{clip.hook}"</p>
          )}

          <a
            href={clipVideoUrl(clip.id)}
            download={`${clip.title}.mp4`}
            className="flex items-center gap-1.5 text-xs text-muted hover:text-neon transition-colors w-fit"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </a>
        </div>
      </div>

      {/* Video modal */}
      {playing && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
          onClick={() => setPlaying(false)}
        >
          <button
            className="absolute top-4 right-4 text-white/70 hover:text-white"
            onClick={() => setPlaying(false)}
          >
            <X className="w-6 h-6" />
          </button>
          <div
            className="relative max-h-[90vh] aspect-[9/16]"
            onClick={(e) => e.stopPropagation()}
          >
            <video
              src={clipVideoUrl(clip.id)}
              controls
              autoPlay
              className="h-full w-full rounded-xl"
            />
          </div>
          <div className="absolute bottom-6 left-0 right-0 text-center">
            <p className="text-white font-medium">{clip.title}</p>
            <p className="text-sm text-white/60 mt-1">{clip.reasoning}</p>
          </div>
        </div>
      )}
    </>
  )
}
