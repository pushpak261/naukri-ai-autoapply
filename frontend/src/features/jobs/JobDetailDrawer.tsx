import type { JobCard } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function JobDetailDrawer({ job, onClose }: { job: JobCard; onClose: () => void }) {
  const isExternal = job.is_external_apply || job.status === 'external_apply'

  return (
    <Card className="mt-4">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{job.title}</CardTitle>
          <p className="text-sm text-muted-foreground">{job.company}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge status={job.status} />
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {isExternal && (
          <div className="rounded-md border border-sky-500/30 bg-sky-500/10 p-3">
            <p className="font-medium text-sky-300">External apply required</p>
            <p className="mt-1 text-xs text-muted-foreground">
              This job redirects to the company career site. Apply manually using the links below.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {job.url && (
                <Button variant="outline" size="sm" asChild>
                  <a href={job.url} target="_blank" rel="noreferrer">
                    View on Naukri
                  </a>
                </Button>
              )}
              {job.external_apply_url ? (
                <Button size="sm" asChild>
                  <a href={job.external_apply_url} target="_blank" rel="noreferrer">
                    Apply on company site
                  </a>
                </Button>
              ) : job.url ? (
                <Button size="sm" asChild>
                  <a href={job.url} target="_blank" rel="noreferrer">
                    Open posting to apply
                  </a>
                </Button>
              ) : null}
            </div>
          </div>
        )}
        {job.match_reasoning && (
          <div>
            <p className="font-medium text-muted-foreground">Match reasoning</p>
            <p>{job.match_reasoning}</p>
          </div>
        )}
        {job.skills && (
          <div>
            <p className="font-medium text-muted-foreground">Skills</p>
            <p>{job.skills}</p>
          </div>
        )}
        {job.reason && (
          <div>
            <p className="font-medium text-muted-foreground">Skip reason</p>
            <p>{job.reason}</p>
          </div>
        )}
        <div className="flex gap-4 text-xs text-muted-foreground">
          {job.is_verified != null && <span>Verified: {job.is_verified ? 'Yes' : 'No'}</span>}
          {job.company_rating != null && <span>Rating: {job.company_rating}</span>}
          {job.hiring_for && <span>Hiring for: {job.hiring_for}</span>}
          {job.is_consultant_post != null && (
            <span>Consultant post: {job.is_consultant_post ? 'Yes' : 'No'}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
