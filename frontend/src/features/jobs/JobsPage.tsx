import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { useAgentEventStream } from '@/hooks/useAgentEventStream'
import { useRunStore } from '@/store/runStore'
import { JobFeed } from './JobFeed'

export function JobsPage() {
  const runId = useRunStore((s) => s.runId)
  const setRunId = useRunStore((s) => s.setRunId)
  const { data: status } = useQuery({
    queryKey: ['run-current'],
    queryFn: runsApi.current,
    refetchInterval: 3000,
  })

  useEffect(() => {
    if (status?.run_id && status.status === 'running') {
      setRunId(status.run_id)
    }
  }, [status?.run_id, status?.status, setRunId])

  const activeRunId = runId ?? status?.run_id ?? null
  useAgentEventStream(activeRunId)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Live Jobs</h1>
        <p className="text-sm text-muted-foreground">
          Real-time job feed during an active run
          {activeRunId ? ` (run #${activeRunId})` : ''}
        </p>
      </div>
      <JobFeed />
    </div>
  )
}
