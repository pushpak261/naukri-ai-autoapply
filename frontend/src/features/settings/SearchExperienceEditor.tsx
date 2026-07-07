import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { jobsApi } from '@/api/jobs'
import type { ConfigSummary } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface SearchExperienceEditorProps {
  config: ConfigSummary
  onSaved?: () => void
  compact?: boolean
}

export function SearchExperienceEditor({
  config,
  onSaved,
  compact = false,
}: SearchExperienceEditorProps) {
  const [experienceMin, setExperienceMin] = useState(String(config.experience_min))
  const [experienceMax, setExperienceMax] = useState(String(config.experience_max))
  const queryClient = useQueryClient()

  useEffect(() => {
    setExperienceMin(String(config.experience_min))
    setExperienceMax(String(config.experience_max))
  }, [config.experience_min, config.experience_max])

  const saveMutation = useMutation({
    mutationFn: () => {
      const minValue = Number(experienceMin)
      const maxValue = Number(experienceMax)
      if (!Number.isFinite(minValue) || minValue < 0 || minValue > 50) {
        throw new Error('Min experience must be between 0 and 50')
      }
      if (!Number.isFinite(maxValue) || maxValue < 0 || maxValue > 50) {
        throw new Error('Max experience must be between 0 and 50')
      }
      if (minValue > maxValue) {
        throw new Error('Min experience cannot be greater than max experience')
      }
      return jobsApi.updateSearchExperience({
        experience_min: minValue,
        experience_max: maxValue,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-summary'] })
      onSaved?.()
    },
  })

  const inputs = (
    <div className="flex flex-wrap items-center gap-4">
      <label className="flex items-center gap-2 text-sm">
        Min years
        <input
          type="number"
          min={0}
          max={50}
          value={experienceMin}
          onChange={(e) => setExperienceMin(e.target.value)}
          className="w-20 rounded border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        Max years
        <input
          type="number"
          min={0}
          max={50}
          value={experienceMax}
          onChange={(e) => setExperienceMax(e.target.value)}
          className="w-20 rounded border border-border bg-background px-2 py-1 text-sm"
        />
      </label>
      {!compact && (
        <Button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          size="sm"
        >
          Save
        </Button>
      )}
    </div>
  )

  if (compact) {
    return (
      <div className="space-y-1">
        {inputs}
        {saveMutation.isError && (
          <p className="text-sm text-destructive">{(saveMutation.error as Error).message}</p>
        )}
      </div>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Search Experience</CardTitle>
        <p className="text-sm text-muted-foreground">
          Set the experience range used when searching and filtering jobs on Naukri.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {inputs}
        <p className="text-xs text-muted-foreground">
          Jobs requiring more than the max years are filtered out. Changes are saved to
          the database.
        </p>
        {saveMutation.isError && (
          <p className="text-sm text-destructive">{(saveMutation.error as Error).message}</p>
        )}
        {saveMutation.isSuccess && (
          <p className="text-sm text-emerald-600">Experience range saved.</p>
        )}
      </CardContent>
    </Card>
  )
}

export function validateExperienceRange(
  experienceMin: string,
  experienceMax: string,
): { experience_min: number; experience_max: number } {
  const minValue = Number(experienceMin)
  const maxValue = Number(experienceMax)
  if (!Number.isFinite(minValue) || minValue < 0 || minValue > 50) {
    throw new Error('Min experience must be between 0 and 50')
  }
  if (!Number.isFinite(maxValue) || maxValue < 0 || maxValue > 50) {
    throw new Error('Max experience must be between 0 and 50')
  }
  if (minValue > maxValue) {
    throw new Error('Min experience cannot be greater than max experience')
  }
  return { experience_min: minValue, experience_max: maxValue }
}
