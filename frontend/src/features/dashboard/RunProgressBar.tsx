import type { RunStatus } from '@/api/types'
import { useRunStore } from '@/store/runStore'

export function RunProgressBar({ status }: { status?: RunStatus }) {
  const liveCounters = useRunStore((s) => s.counters)
  const phase = useRunStore((s) => s.phase)

  const processed = liveCounters.processed_count ?? status?.processed_count ?? 0
  const total = liveCounters.total_queued ?? status?.total_queued ?? status?.jobs_found ?? 0
  const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Phase: {phase || status?.phase || 'idle'}</span>
        <span>
          {processed} / {total} ({pct}%)
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
