import type { RunStatus } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useRunStore } from '@/store/runStore'

const stats = [
  { key: 'jobs_found', label: 'Found' },
  { key: 'jobs_applied', label: 'Applied' },
  { key: 'jobs_skipped', label: 'Skipped' },
  { key: 'jobs_failed', label: 'Failed' },
  { key: 'daily_cap_remaining', label: 'Cap Left' },
] as const

export function LiveStatsCards({ status }: { status?: RunStatus }) {
  const liveCounters = useRunStore((s) => s.counters)

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {stats.map(({ key, label }) => (
        <Card key={key}>
          <CardHeader className="p-3 pb-1">
            <CardTitle className="text-xs font-normal text-muted-foreground">{label}</CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-0 text-2xl font-bold">
            {liveCounters[key] ?? status?.[key] ?? 0}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
