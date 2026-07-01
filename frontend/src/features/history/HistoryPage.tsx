import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { runsApi } from '@/api/runs'
import { Skeleton } from '@/components/ui/skeleton'
import { ApplicationsTable } from './ApplicationsTable'
import { RunHistoryTable } from './RunHistoryTable'

export function HistoryPage() {
  const runsQuery = useQuery({ queryKey: ['runs'], queryFn: () => runsApi.list(20) })
  const appsQuery = useQuery({
    queryKey: ['applications'],
    queryFn: () => jobsApi.recentApplications(30),
  })

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">History</h1>
        <p className="text-sm text-muted-foreground">Past runs and applications from SQLite</p>
      </div>

      {runsQuery.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : (
        <RunHistoryTable runs={runsQuery.data ?? []} />
      )}

      {appsQuery.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <ApplicationsTable applications={appsQuery.data ?? []} />
      )}
    </div>
  )
}
