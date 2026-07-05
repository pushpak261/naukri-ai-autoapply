import { useQuery } from '@tanstack/react-query'
import { jobsApi } from '@/api/jobs'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfigSummary } from './ConfigSummary'
import { SearchExperienceEditor } from './SearchExperienceEditor'

export function SettingsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['config-summary'],
    queryFn: jobsApi.configSummary,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure search filters and view your agent configuration.
        </p>
      </div>
      {isLoading && <Skeleton className="h-64 w-full" />}
      {isError && (
        <Card>
          <CardContent className="p-8 text-destructive">Failed to load configuration.</CardContent>
        </Card>
      )}
      {data && (
        <>
          <SearchExperienceEditor config={data} />
          <ConfigSummary config={data} />
        </>
      )}
    </div>
  )
}
