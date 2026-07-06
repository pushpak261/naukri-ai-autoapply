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
    <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5 hover:border-[#38bdf8]/30 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-[#94a3b8] font-medium">{title}</p>
          <p className="text-2xl font-bold text-white mt-1" style={{ color }}>{value}</p>
          {subtitle && <p className="text-xs text-[#64748b] mt-1">{subtitle}</p>}
        </div>
        <div className="p-2.5 rounded-lg" style={{ backgroundColor: `${color}15` }}>
          <Icon className="w-5 h-5" style={{ color }} />
        </div>
      </div>
    </div>
  );
}
