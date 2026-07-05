import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Square } from 'lucide-react'
import { useEffect, useState } from 'react'
import { jobsApi } from '@/api/jobs'
import { runsApi } from '@/api/runs'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { validateExperienceRange } from '@/features/settings/SearchExperienceEditor'
import { useRunStore } from '@/store/runStore'
import { LiveStatsCards } from './LiveStatsCards'
import { RunProgressBar } from './RunProgressBar'

export function RunControls() {
  const [dryRun, setDryRun] = useState(true)
  const [cap, setCap] = useState('')
  const [threshold, setThreshold] = useState('')
  const [experienceMin, setExperienceMin] = useState('')
  const [experienceMax, setExperienceMax] = useState('')
  const queryClient = useQueryClient()
  const setRunId = useRunStore((s) => s.setRunId)
  const reset = useRunStore((s) => s.reset)

  const { data: config } = useQuery({
    queryKey: ['config-summary'],
    queryFn: jobsApi.configSummary,
  })

  useEffect(() => {
    if (!config) return
    setCap(String(config.daily_cap))
    setThreshold(String(config.match_score_threshold))
    setExperienceMin(String(config.experience_min))
    setExperienceMax(String(config.experience_max))
  }, [config])
  const { data: status } = useQuery({
    queryKey: ['run-current'],
    queryFn: runsApi.current,
    refetchInterval: 2000,
  })

  const isRunning = status?.status === 'running'
  const showLoginBanner = isRunning && status?.phase === 'logging_in'

  const startMutation = useMutation({
    mutationFn: () => {
      const capValue = Number(cap)
      const thresholdValue = Number(threshold)
      const experience = validateExperienceRange(experienceMin, experienceMax)
      if (!Number.isFinite(capValue) || capValue < 1) {
        throw new Error('Cap must be a number of at least 1')
      }
      if (!Number.isFinite(thresholdValue) || thresholdValue < 0 || thresholdValue > 100) {
        throw new Error('Threshold must be between 0 and 100')
      }
      return runsApi.start({
        dry_run: dryRun,
        cap: capValue,
        threshold: thresholdValue,
        experience_min: experience.experience_min,
        experience_max: experience.experience_max,
      })
    },
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
              min={1}
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              placeholder={config ? String(config.daily_cap) : '30'}
              className="w-20 rounded border border-border bg-background px-2 py-1 text-sm"
            />
            <span className="text-xs text-muted-foreground">max applies this run</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            Threshold
            <input
              type="number"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder={config ? String(config.match_score_threshold) : '50'}
              className="w-20 rounded border border-border bg-background px-2 py-1 text-sm"
            />
            <span className="text-xs text-muted-foreground">min match %</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            Experience
            <input
              type="number"
              min={0}
              max={50}
              value={experienceMin}
              onChange={(e) => setExperienceMin(e.target.value)}
              placeholder={config ? String(config.experience_min) : '0'}
              className="w-16 rounded border border-border bg-background px-2 py-1 text-sm"
            />
            <span className="text-muted-foreground">–</span>
            <input
              type="number"
              min={0}
              max={50}
              value={experienceMax}
              onChange={(e) => setExperienceMax(e.target.value)}
              placeholder={config ? String(config.experience_max) : '5'}
              className="w-16 rounded border border-border bg-background px-2 py-1 text-sm"
            />
            <span className="text-xs text-muted-foreground">years for search</span>
          </label>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={() => startMutation.mutate()}
            disabled={isRunning || startMutation.isPending || !config}
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
