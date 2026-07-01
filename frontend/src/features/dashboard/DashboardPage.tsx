import { RunControls } from './RunControls'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { useAgentEventStream } from '@/hooks/useAgentEventStream'
import { useRunStore } from '@/store/runStore'
import { useEffect } from 'react'

export function DashboardPage() {
  const runId = useRunStore((s) => s.runId)
  const setRunId = useRunStore((s) => s.setRunId)
  const { data: status } = useQuery({
    queryKey: ['run-current'],
    queryFn: runsApi.current,
    refetchInterval: 2000,
  })

  useEffect(() => {
    if (status?.run_id && status.status === 'running') {
      setRunId(status.run_id)
    }
  }, [status?.run_id, status?.status, setRunId])

  useAgentEventStream(runId ?? status?.run_id ?? null)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Start and monitor the Naukri AI agent</p>
      </div>
      <RunControls />
    </div>
  )
}
