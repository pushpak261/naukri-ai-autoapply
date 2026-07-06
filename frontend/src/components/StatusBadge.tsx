interface StatusBadgeProps {
  status: string;
  className?: string;
}

const statusColors: Record<string, string> = {
  applied: 'bg-green-500/15 text-green-400 border-green-500/30',
  skipped_low_score: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  skipped_excluded: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  skipped_already_applied: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  skipped_external: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  skipped_screening: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  skipped_dry_run: 'bg-teal-500/15 text-teal-400 border-teal-500/30',
  uncertain: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  failed: 'bg-red-500/15 text-red-400 border-red-500/30',
  error: 'bg-red-500/15 text-red-400 border-red-500/30',
  running: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  completed: 'bg-green-500/15 text-green-400 border-green-500/30',
  interrupted: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
};

const statusLabels: Record<string, string> = {
  applied: 'Applied',
  skipped_low_score: 'Low Score',
  skipped_excluded: 'Excluded',
  skipped_already_applied: 'Duplicate',
  skipped_external: 'External',
  skipped_screening: 'Screening',
  skipped_dry_run: 'Dry Run',
  uncertain: 'Uncertain',
  failed: 'Failed',
  error: 'Error',
  running: 'Running',
  completed: 'Completed',
  interrupted: 'Interrupted',
};

export default function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const color = statusColors[status] || 'bg-gray-500/15 text-gray-400 border-gray-500/30';
  const label = statusLabels[status] || status;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${color} ${className}`}>
      {label}
    </span>
  );
}
