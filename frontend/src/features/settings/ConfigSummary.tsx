import type { ConfigSummary as ConfigSummaryType } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function ConfigSummary({ config }: { config: ConfigSummaryType }) {
  const rows: Array<[string, string | number | boolean]> = [
    ['Strict policy mode', config.strict_policy_mode ? 'Enabled' : 'Disabled'],
    ['Role source', config.role_source],
    ['Experience source', config.experience_source],
    ['Keywords', config.keywords.join(', ')],
    ['Locations', config.locations.join(', ')],
    ['Experience', `${config.experience_min}–${config.experience_max} yrs`],
    ['Freshness window', `${config.freshness_days} days`],
    ['Daily cap', config.daily_cap],
    ['Match threshold', `${config.match_score_threshold}%`],
    ['Dry run', config.dry_run ? 'Yes' : 'No'],
    ['Min company rating', config.min_company_rating],
    ['Apply workers', config.apply_workers ?? 1],
    ['AI model', config.ai_model],
    ['Excluded companies', config.excluded_companies.join(', ') || '—'],
    ['Excluded title keywords', config.excluded_title_keywords.join(', ') || '—'],
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="rounded-md border border-border p-3">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd className="mt-1 text-sm">{String(value)}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
