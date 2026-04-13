import clsx from 'clsx'

interface Props {
  score: number
  size?: 'sm' | 'md'
}

export default function ScoreBadge({ score, size = 'md' }: Props) {
  const color =
    score >= 8 ? 'text-neon border-neon/30 bg-neon/10' :
    score >= 6 ? 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10' :
                 'text-red-400 border-red-400/30 bg-red-400/10'

  return (
    <span
      className={clsx(
        'inline-flex items-center font-mono font-bold rounded border',
        size === 'sm' ? 'text-xs px-1.5 py-0.5' : 'text-sm px-2 py-1',
        color
      )}
    >
      {score.toFixed(1)}
    </span>
  )
}
