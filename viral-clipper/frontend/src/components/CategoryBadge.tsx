import clsx from 'clsx'
import type { Category } from '../api'

const COLORS: Record<string, string> = {
  humor:       'bg-yellow-400/10 text-yellow-300 border-yellow-400/20',
  shock:       'bg-red-500/10 text-red-300 border-red-500/20',
  insight:     'bg-blue-500/10 text-blue-300 border-blue-500/20',
  drama:       'bg-purple-500/10 text-purple-300 border-purple-500/20',
  motivation:  'bg-neon/10 text-neon border-neon/20',
  controversy: 'bg-orange-500/10 text-orange-300 border-orange-500/20',
}

interface Props {
  category: string
}

export default function CategoryBadge({ category }: Props) {
  const cls = COLORS[category] ?? 'bg-white/5 text-white/60 border-white/10'
  return (
    <span className={clsx('text-xs px-2 py-0.5 rounded border font-medium capitalize', cls)}>
      {category}
    </span>
  )
}
