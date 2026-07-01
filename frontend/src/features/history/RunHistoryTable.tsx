import type { RunSummary } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function RunHistoryTable({ runs }: { runs: RunSummary[] }) {
  if (runs.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-muted-foreground">No runs recorded yet.</CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Run History</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="pb-2 pr-4">ID</th>
              <th className="pb-2 pr-4">Started</th>
              <th className="pb-2 pr-4">Keywords</th>
              <th className="pb-2 pr-4">Found</th>
              <th className="pb-2 pr-4">Applied</th>
              <th className="pb-2 pr-4">Skipped</th>
              <th className="pb-2 pr-4">Failed</th>
              <th className="pb-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-b border-border/50">
                <td className="py-2 pr-4">#{run.id}</td>
                <td className="py-2 pr-4 text-xs">{new Date(run.started_at).toLocaleString()}</td>
                <td className="py-2 pr-4 text-xs">{run.keywords.join(', ')}</td>
                <td className="py-2 pr-4">{run.found}</td>
                <td className="py-2 pr-4">{run.applied}</td>
                <td className="py-2 pr-4">{run.skipped}</td>
                <td className="py-2 pr-4">{run.failed}</td>
                <td className="py-2 capitalize">{run.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}
