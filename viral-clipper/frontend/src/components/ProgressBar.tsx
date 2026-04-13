import clsx from 'clsx'

const STEPS = ['downloading', 'transcribing', 'analyzing', 'clipping', 'done']

function stepIndex(step: string) {
  const clean = step.toLowerCase().replace(/\s.*/, '')
  const idx = STEPS.findIndex((s) => clean.startsWith(s))
  return idx >= 0 ? idx : 0
}

interface Props {
  step: string
  progress: number
  status: string
}

export default function ProgressBar({ step, progress, status }: Props) {
  const currentIdx = stepIndex(step)
  const isError = status === 'error'
  const isDone = status === 'done'

  return (
    <div className="space-y-3">
      {/* Step labels */}
      <div className="flex justify-between text-xs text-muted">
        {STEPS.filter((s) => s !== 'done').map((s, i) => (
          <span
            key={s}
            className={clsx(
              'capitalize transition-colors',
              i < currentIdx ? 'text-neon' : i === currentIdx ? 'text-white' : ''
            )}
          >
            {s}
          </span>
        ))}
      </div>

      {/* Bar */}
      <div className="h-1.5 bg-border rounded-full overflow-hidden">
        <div
          className={clsx(
            'h-full rounded-full transition-all duration-500',
            isError ? 'bg-red-500' : isDone ? 'bg-neon' : 'bg-neon neon-pulse'
          )}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Current step */}
      <p className="text-xs text-muted text-center capitalize">{step}</p>
    </div>
  )
}
