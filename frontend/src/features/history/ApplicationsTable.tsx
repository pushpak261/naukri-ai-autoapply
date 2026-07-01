import type { ApplicationRecord } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ExternalLink } from 'lucide-react'

export function ApplicationsTable({ applications }: { applications: ApplicationRecord[] }) {
  if (applications.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">
          No applications recorded yet.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Applications</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="pb-2 pr-4">Role</th>
              <th className="pb-2 pr-4">Company</th>
              <th className="pb-2 pr-4">Score</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2 pr-4">Date</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {applications.map((app, i) => (
              <tr key={`${app.url}-${i}`} className="border-b border-border/50">
                <td className="py-2 pr-4">{app.job_title}</td>
                <td className="py-2 pr-4 text-muted-foreground">{app.company}</td>
                <td className="py-2 pr-4">{Math.round(app.match_score)}</td>
                <td className="py-2 pr-4">
                  <Badge status={app.status} />
                </td>
                <td className="py-2 pr-4 text-xs">
                  {app.applied_at ? new Date(app.applied_at).toLocaleString() : '—'}
                </td>
                <td className="py-2">
                  {app.url && (
                    <a href={app.url} target="_blank" rel="noreferrer" className="text-primary">
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}
