import type { RunStatus } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function LiveAppliedJobs({ status }: { status?: RunStatus }) {
  const appliedJobs = status?.applied_jobs ?? []
  if (!status || status.status !== 'running' || appliedJobs.length === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          Applied This Run ({appliedJobs.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-64 space-y-2 overflow-y-auto">
        {appliedJobs.map((job, index) => (
          <div
            key={job.naukri_job_id || `${job.title}-${index}`}
            className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{job.title}</p>
              <p className="truncate text-xs text-muted-foreground">
                {job.company}
                {job.location ? ` · ${job.location}` : ''}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {job.match_score != null && (
                <span className="text-xs font-semibold text-emerald-500">
                  {Math.round(job.match_score)}
                </span>
              )}
              {job.url ? (
                <a
                  href={job.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-primary hover:underline"
                >
                  View
                </a>
              ) : null}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
