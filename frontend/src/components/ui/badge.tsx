import { cn } from '@/lib/utils'

const statusColors: Record<string, string> = {
  applied: 'bg-emerald-500/20 text-emerald-300',
  discovered: 'bg-blue-500/20 text-blue-300',
  queued: 'bg-slate-500/20 text-slate-300',
  processing: 'bg-cyan-500/20 text-cyan-300',
  matching: 'bg-violet-500/20 text-violet-300',
  applying: 'bg-amber-500/20 text-amber-300',
  failed: 'bg-red-500/20 text-red-300',
  skipped_low_score: 'bg-orange-500/20 text-orange-300',
  skipped_dry_run: 'bg-yellow-500/20 text-yellow-300',
  skipped_already_applied: 'bg-zinc-500/20 text-zinc-300',
  skipped_excluded: 'bg-zinc-500/20 text-zinc-300',
  skipped_quality: 'bg-zinc-500/20 text-zinc-300',
  skipped_similarity: 'bg-zinc-500/20 text-zinc-300',
  skipped_not_big_company: 'bg-zinc-500/20 text-zinc-300',
  skipped_consultancy_recruiter: 'bg-rose-500/20 text-rose-300',
  skipped_low_company_rating: 'bg-orange-500/20 text-orange-300',
  skipped_external: 'bg-sky-500/20 text-sky-300',
  external_apply: 'bg-sky-500/20 text-sky-300',
}

export function Badge({ status, className }: { status: string; className?: string }) {
  const color = statusColors[status] || 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex rounded-full px-2 py-0.5 text-xs font-medium', color, className)}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}
