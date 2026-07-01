import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfigSummary } from './ConfigSummary'

export function SettingsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['config-summary'],
    queryFn: jobsApi.configSummary,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">Read-only view of config.yaml (edit in v2)</p>
      </div>
      {isLoading && <Skeleton className="h-64 w-full" />}
      {isError && (
        <Card>
          <CardContent className="p-8 text-destructive">Failed to load configuration.</CardContent>
        </Card>
      )}
      {data && <ConfigSummary config={data} />}
    </div>
  )
}
