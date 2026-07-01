import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Square } from 'lucide-react'
import { useState } from 'react'
import { runsApi } from '@/api/runs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { useRunStore } from '@/store/runStore'
import { LiveStatsCards } from './LiveStatsCards'
import { RunProgressBar } from './RunProgressBar'

export function RunControls() {
  const [dryRun, setDryRun] = useState(true)
  const [cap, setCap] = useState('')
  const [threshold, setThreshold] = useState('')
  const queryClient = useQueryClient()
  const setRunId = useRunStore((s) => s.setRunId)
  const reset = useRunStore((s) => s.reset)

  const { data: status } = useQuery({
    queryKey: ['run-current'],
    queryFn: runsApi.current,
    refetchInterval: 2000,
  })

  const isRunning = status?.status === 'running'
  const showLoginBanner = isRunning && status?.phase === 'logging_in'

  const startMutation = useMutation({
    mutationFn: () =>
      runsApi.start({
        dry_run: dryRun,
        cap: cap ? Number(cap) : null,
        threshold: threshold ? Number(threshold) : null,
      }),
    onSuccess: (data) => {
      reset()
      if (data.run_id) setRunId(data.run_id)
      queryClient.invalidateQueries({ queryKey: ['run-current'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: runsApi.stop,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['run-current'] }),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Run Controls</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {showLoginBanner && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            Complete login/OTP in the Chromium window that opens on your desktop.
          </div>
        )}

        {status?.error && (
          <p className="text-sm text-destructive">{status.error}</p>
        )}

        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={dryRun} onCheckedChange={setDryRun} id="dry-run" />
            Dry run
          </label>
          <label className="flex items-center gap-2 text-sm">
            Cap
            <input
              type="number"
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              placeholder="default"
              className="w-20 rounded border border-border bg-background px-2 py-1 text-sm"
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            Threshold
            <input
              type="number"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="default"
              className="w-20 rounded border border-border bg-background px-2 py-1 text-sm"
            />
          </label>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={() => startMutation.mutate()}
            disabled={isRunning || startMutation.isPending}
          >
            <Play className="mr-2 h-4 w-4" />
            Start Run
          </Button>
          <Button
            variant="destructive"
            onClick={() => stopMutation.mutate()}
            disabled={!isRunning || stopMutation.isPending}
          >
            <Square className="mr-2 h-4 w-4" />
            Stop
          </Button>
        </div>

        {startMutation.isError && (
          <p className="text-sm text-destructive">{(startMutation.error as Error).message}</p>
        )}

        {status && (
          <div className="text-sm text-muted-foreground">
            Status: <span className="text-foreground">{status.status}</span>
            {status.phase && (
              <>
                {' '}
                · Phase: <span className="text-foreground">{status.phase}</span>
              </>
            )}
            {status.run_id && (
              <>
                {' '}
                · Run #{status.run_id}
              </>
            )}
          </div>
        )}

        <LiveStatsCards status={status} />
        <RunProgressBar status={status} />
      </CardContent>
    </Card>
  )
}
