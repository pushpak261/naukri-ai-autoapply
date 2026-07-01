import { useVirtualizer } from '@tanstack/react-virtual'
import { Building2, ExternalLink } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import type { JobCard } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { useRunStore } from '@/store/runStore'
import { JobDetailDrawer } from './JobDetailDrawer'

type Filter = 'all' | 'applied' | 'skipped' | 'failed' | 'matching' | 'external'

const FILTER_STATUSES: Record<Filter, (s: string) => boolean> = {
  all: () => true,
  applied: (s) => s === 'applied',
  skipped: (s) => s.startsWith('skipped'),
  failed: (s) => s === 'failed',
  matching: (s) => ['matching', 'applying', 'processing'].includes(s),
  external: (s) => s === 'external_apply',
}

export function JobFeed() {
  const jobsMap = useRunStore((s) => s.jobs)
  const expandedJobId = useRunStore((s) => s.expandedJobId)
  const setExpandedJobId = useRunStore((s) => s.setExpandedJobId)
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const parentRef = useRef<HTMLDivElement>(null)

  const jobs = useMemo(() => {
    const list = Array.from(jobsMap.values())
    const q = search.toLowerCase()
    return list
      .filter((j) => FILTER_STATUSES[filter](j.status))
      .filter(
        (j) =>
          !q ||
          j.title.toLowerCase().includes(q) ||
          j.company.toLowerCase().includes(q),
      )
      .sort((a, b) => a.title.localeCompare(b.title))
  }, [jobsMap, filter, search])

  const rowVirtualizer = useVirtualizer({
    count: jobs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 52,
    overscan: 10,
  })

  const expandedJob = expandedJobId ? jobsMap.get(expandedJobId) : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {(['all', 'applied', 'skipped', 'failed', 'matching', 'external'] as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`rounded-full px-3 py-1 text-xs capitalize ${
              filter === f ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'
            }`}
          >
            {f}
          </button>
        ))}
        <input
          type="search"
          placeholder="Search title or company..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="ml-auto rounded border border-border bg-background px-3 py-1 text-sm"
        />
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Auto-scroll
        </label>
      </div>

      {jobs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-12 text-center text-muted-foreground">
          No jobs yet. Start a run from the Dashboard to see live updates.
        </div>
      ) : (
        <div
          ref={parentRef}
          className="h-[calc(100vh-280px)] overflow-auto rounded-lg border border-border"
        >
          <div className="sticky top-0 z-10 grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr_80px_100px_72px] gap-2 border-b border-border bg-card px-4 py-2 text-xs font-medium text-muted-foreground">
            <span>Role</span>
            <span>Company</span>
            <span>Location</span>
            <span>Exp</span>
            <span>Salary</span>
            <span>Score</span>
            <span>Status</span>
            <span>Links</span>
          </div>
          <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const job = jobs[virtualRow.index] as JobCard
              return (
                <JobRow
                  key={job.naukri_job_id}
                  job={job}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: virtualRow.size,
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                  onExpand={() =>
                    setExpandedJobId(
                      expandedJobId === job.naukri_job_id ? null : job.naukri_job_id,
                    )
                  }
                  expanded={expandedJobId === job.naukri_job_id}
                />
              )
            })}
          </div>
        </div>
      )}

      {expandedJob && <JobDetailDrawer job={expandedJob} onClose={() => setExpandedJobId(null)} />}
    </div>
  )
}

function JobRow({
  job,
  style,
  onExpand,
  expanded,
}: {
  job: JobCard
  style: React.CSSProperties
  onExpand: () => void
  expanded: boolean
}) {
  const score = job.match_score ?? job.heuristic_score
  return (
    <>
      <div
        style={style}
        className={`grid grid-cols-[2fr_1.5fr_1fr_1fr_1fr_80px_100px_72px] items-center gap-2 border-b border-border px-4 py-2 text-sm hover:bg-accent/50 ${
          expanded ? 'bg-accent/30' : ''
        }`}
        onClick={onExpand}
        onKeyDown={(e) => e.key === 'Enter' && onExpand()}
        role="button"
        tabIndex={0}
      >
        <span className="truncate font-medium">{job.title}</span>
        <span className="truncate text-muted-foreground">{job.company}</span>
        <span className="truncate text-xs">{job.location || '—'}</span>
        <span className="truncate text-xs">{job.experience || '—'}</span>
        <span className="truncate text-xs">{job.salary || '—'}</span>
        <span className="text-xs">{score != null ? Math.round(score) : '—'}</span>
        <Badge status={job.status} />
        <div className="flex items-center gap-1">
          {job.url ? (
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              title="Naukri posting"
              onClick={(e) => e.stopPropagation()}
              className="text-primary hover:opacity-80"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          ) : null}
          {job.external_apply_url ? (
            <a
              href={job.external_apply_url}
              target="_blank"
              rel="noreferrer"
              title="Apply on company site"
              onClick={(e) => e.stopPropagation()}
              className="text-sky-400 hover:opacity-80"
            >
              <Building2 className="h-4 w-4" />
            </a>
          ) : null}
        </div>
      </div>
    </>
  )
}
