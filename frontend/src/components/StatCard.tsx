import { type LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  color?: string;
  subtitle?: string;
}

export default function StatCard({ title, value, icon: Icon, color = '#38bdf8', subtitle }: StatCardProps) {
  return (
    <div className="shared-stat">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm muted font-medium">{title}</p>
          <p className="text-2xl font-bold  mt-1" style={{ color }}>{value}</p>
          {subtitle && <p className="text-xs muted mt-1">{subtitle}</p>}
        </div>
        <div className="p-2.5 rounded-lg" style={{ backgroundColor: `${color}15` }}>
          <Icon className="w-5 h-5" style={{ color }} />
        </div>
      </div>
    </div>
  );
}
