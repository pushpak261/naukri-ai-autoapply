import { type LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  color?: string;
  subtitle?: string;
}

export default function StatCard({ title, value, icon: Icon, color, subtitle }: StatCardProps) {
  const accent = color ?? 'var(--color-primary)';

  return (
    <div className="card card-hover p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-secondary font-medium">{title}</p>
          <p className="text-2xl font-bold text-text mt-1" style={{ color: color ?? undefined }}>{value}</p>
          {subtitle && <p className="text-xs text-muted mt-1">{subtitle}</p>}
        </div>
        <div className="p-2.5 rounded-lg" style={{ backgroundColor: `color-mix(in srgb, ${accent} 15%, transparent)` }}>
          <Icon className="w-5 h-5" style={{ color: accent }} />
        </div>
      </div>
    </div>
  );
}
