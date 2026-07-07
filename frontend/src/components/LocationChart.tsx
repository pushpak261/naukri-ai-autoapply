import { useState, useMemo, useRef } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts';
import {
  MapPin, Search, ArrowUpDown, Expand, Download, BugOff,
} from 'lucide-react';
import type { LocationDistribution } from '../lib/api';

const COLORS = [
  '#38bdf8', '#22c55e', '#a855f7', '#f97316', '#ec4899',
  '#06b6d4', '#84cc16', '#f59e0b', '#6366f1', '#14b8a6',
  '#e11d48', '#0ea5e9', '#d946ef', '#fbbf24', '#34d399',
];

const TOP_N = 10;

function prepareChartData(
  items: LocationDistribution[],
  search: string,
  sortBy: 'count' | 'name',
  expanded = false,
) {
  const filtered = search
    ? items.filter(l => l.location.toLowerCase().includes(search.toLowerCase()))
    : items;

  if (filtered.length === 0) return { chart: [], others: [], totalLocations: 0, totalJobs: 0 };

  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'name') return a.location.localeCompare(b.location);
    return b.count - a.count;
  });

  const totalJobs = sorted.reduce((s, l) => s + l.count, 0);

  if (!expanded && sorted.length > TOP_N + 1) {
    const top = sorted.slice(0, TOP_N);
    const rest = sorted.slice(TOP_N);
    const othersCount = rest.reduce((s, l) => s + l.count, 0);
    const chart = [
      ...top,
      { location: `Others (${rest.length})`, count: othersCount },
    ];
    return { chart, others: rest, totalLocations: filtered.length, totalJobs };
  }

  return { chart: sorted, others: [], totalLocations: filtered.length, totalJobs };
}

function exportCSV(items: LocationDistribution[], totalJobs: number) {
  const headers = 'Location,Count,Percentage\n';
  const rows = items
    .map(l => `${l.location},${l.count},${totalJobs > 0 ? ((l.count / totalJobs) * 100).toFixed(1) : 0}%`)
    .join('\n');
  const blob = new Blob([headers + rows], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'location-distribution.csv';
  a.click();
  URL.revokeObjectURL(url);
}

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="flex gap-2">
        <div className="h-8 bg-surface-hover rounded-lg flex-1" />
        <div className="h-8 w-20 bg-surface-hover rounded-lg" />
        <div className="h-8 w-20 bg-surface-hover rounded-lg" />
      </div>
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-4 bg-surface-hover rounded w-24" />
          <div className="h-4 bg-surface-hover rounded flex-1" />
        </div>
      ))}
    </div>
  );
}

interface Props {
  data: LocationDistribution[];
  loading?: boolean;
}

export default function LocationChart({ data, loading }: Props) {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<'count' | 'name'>('count');
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { chart, others, totalLocations, totalJobs } = useMemo(
    () => prepareChartData(data, search, sortBy, expanded),
    [data, search, sortBy, expanded],
  );

  const toggleFullscreen = async () => {
    if (!fullscreen) {
      await containerRef.current?.requestFullscreen();
      setFullscreen(true);
    } else {
      await document.exitFullscreen();
      setFullscreen(false);
    }
  };

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: LocationDistribution & { isOthers?: boolean } }> }) => {
    if (!active || !payload?.length) return null;
    const entry = payload[0].payload;
    const pct = totalJobs > 0 ? ((entry.count / totalJobs) * 100).toFixed(1) : '0';
    return (
      <div className="bg-surface border border-border rounded-lg px-4 py-3 shadow-xl">
        <p className="text-text font-medium text-sm">{entry.location}</p>
        <p className="text-secondary text-xs mt-1">
          {entry.count} job{entry.count !== 1 ? 's' : ''} — {pct}%
        </p>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="bg-surface rounded-xl border border-border p-5">
        <div className="h-5 w-40 bg-surface-hover rounded mb-4 animate-pulse" />
        <Skeleton />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="bg-surface rounded-xl border border-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <MapPin className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text">Location Distribution</h2>
        </div>
        <div className="flex flex-col items-center justify-center h-64 text-muted gap-3">
          <BugOff className="w-10 h-10" />
          <p className="text-sm">No location data available</p>
        </div>
      </div>
    );
  }

  const totalItemsDisplay = search ? totalLocations : data.length;

  return (
    <div
      ref={containerRef}
      className={`bg-surface rounded-xl border border-border p-5 transition-all ${
        fullscreen ? 'fixed inset-0 z-50 rounded-none overflow-auto' : ''
      }`}
    >
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h2 className="text-lg font-semibold text-text flex items-center gap-2">
          <MapPin className="w-5 h-5 text-primary" />
          Location Distribution
        </h2>
        <div className="flex items-center gap-1.5">
          <button
            onClick={toggleFullscreen}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-muted hover:text-text transition-colors"
            aria-label="Toggle fullscreen"
          >
            <Expand className="w-4 h-4" />
          </button>
          <button
            onClick={() => exportCSV(expanded ? chart : data, totalJobs)}
            className="p-1.5 rounded-lg hover:bg-surface-hover text-muted hover:text-text transition-colors"
            aria-label="Export CSV"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted mb-4">
        <span>{totalItemsDisplay} location{totalItemsDisplay !== 1 ? 's' : ''}</span>
        <span>&middot;</span>
        <span>{totalJobs} job{totalJobs !== 1 ? 's' : ''}</span>
      </div>

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="flex items-center gap-2 bg-bg border border-border rounded-lg px-3 py-1.5 flex-1 min-w-[160px]">
          <Search className="w-4 h-4 text-muted shrink-0" />
          <input
            type="text"
            placeholder="Filter locations..."
            value={search}
            onChange={e => { setSearch(e.target.value); setHighlighted(null); }}
            className="bg-transparent border-none outline-none text-text placeholder:text-muted w-full text-sm"
            aria-label="Filter locations"
          />
        </div>
        <button
          onClick={() => setSortBy(s => (s === 'count' ? 'name' : 'count'))}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-bg border border-border rounded-lg text-xs text-secondary hover:text-text hover:border-border transition-colors"
          aria-label={`Sort by ${sortBy === 'count' ? 'name' : 'count'}`}
        >
          <ArrowUpDown className="w-3.5 h-3.5" />
          {sortBy === 'count' ? 'Count' : 'Name'}
        </button>
        {!search && chart.some(c => c.location.startsWith('Others')) && (
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-xs text-primary hover:underline"
          >
            {expanded ? 'Collapse' : `Show all (${data.length})`}
          </button>
        )}
      </div>

      {chart.length > 0 ? (
        <ResponsiveContainer width="100%" height={fullscreen ? Math.max(chart.length * 40, 400) : 320}>
          <BarChart
            data={chart}
            layout="vertical"
            barCategoryGap="20%"
            onClick={(e) => {
              const label = e?.activeLabel;
              if (label != null) setHighlighted(h => (h === String(label) ? null : String(label)));
            }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
            <YAxis
              type="category"
              dataKey="location"
              width={Math.max(80, Math.min(180, Math.max(...chart.map(c => c.location.length)) * 8))}
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              tickFormatter={(val: string) => val.length > 20 ? val.slice(0, 20) + '…' : val}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(56, 189, 248, 0.08)' }} />
            <Bar dataKey="count" radius={[0, 4, 4, 0]} minPointSize={3}>
              {chart.map((entry, i) => (
                <Cell
                  key={entry.location}
                  fill={
                    highlighted
                      ? highlighted === entry.location
                        ? COLORS[i % COLORS.length]
                        : 'rgba(148, 163, 184, 0.2)'
                      : COLORS[i % COLORS.length]
                  }
                  opacity={
                    highlighted
                      ? highlighted === entry.location
                        ? 1
                        : 0.3
                      : 1
                  }
                  className="transition-opacity duration-200"
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex flex-col items-center justify-center h-64 text-muted gap-2">
          <Search className="w-8 h-8" />
          <p className="text-sm">No locations match your search</p>
        </div>
      )}

      {!search && others.length > 0 && !expanded && (
        <details className="mt-3 group">
          <summary className="text-xs text-secondary cursor-pointer hover:text-text transition-colors select-none">
            {others.length} hidden location{others.length !== 1 ? 's' : ''} ({others.reduce((s, l) => s + l.count, 0)} jobs)
          </summary>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {others.map(l => (
              <span
                key={l.location}
                className="px-2 py-0.5 rounded-full text-xs bg-surface-hover text-secondary"
                title={`${l.count} jobs`}
              >
                {l.location} ({l.count})
              </span>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
