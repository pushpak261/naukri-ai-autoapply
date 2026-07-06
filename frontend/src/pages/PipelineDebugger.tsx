import { useMemo, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  type Node,
  type Edge,
} from '@xyflow/react';
import { Search, Filter, BarChart3, Send, Activity } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

interface StageInfo {
  id: string;
  label: string;
  icon: string;
  description: string;
  status: 'active' | 'completed' | 'pending' | 'error';
  details: string;
}

const PIPELINE_STAGES: StageInfo[] = [
  { id: 'search', label: 'Search Jobs', icon: 'search', description: 'Scrapes Naukri for matching jobs', status: 'completed', details: 'Searches based on configured keywords and locations' },
  { id: 'filter', label: 'Filter & Dedupe', icon: 'filter', description: 'Removes already-applied and excluded jobs', status: 'completed', details: 'Cross-references application history and blacklist' },
  { id: 'score', label: 'AI Match Score', icon: 'score', description: 'Scores jobs against your resume', status: 'active', details: 'Uses LLM to compare job description with resume' },
  { id: 'screen', label: 'Screening Questions', icon: 'screen', description: 'Answers application questions', status: 'pending', details: 'Fills in company-specific screening questions via AI' },
  { id: 'apply', label: 'Submit Application', icon: 'send', description: 'Submits the application on Naukri', status: 'pending', details: 'Fills form and clicks submit' },
];

const ICON_MAP: Record<string, React.ReactNode> = {
  search: <Search className="w-5 h-5" />,
  filter: <Filter className="w-5 h-5" />,
  score: <BarChart3 className="w-5 h-5" />,
  screen: <Activity className="w-5 h-5" />,
  send: <Send className="w-5 h-5" />,
};

function PipelineNode({ data }: { data: StageInfo & { expanded: boolean; onToggle: () => void } }) {
  const statusColors = {
    completed: { border: '#22c55e', bg: 'rgba(34, 197, 94, 0.1)', text: '#22c55e' },
    active: { border: '#38bdf8', bg: 'rgba(56, 189, 248, 0.1)', text: '#38bdf8' },
    pending: { border: '#334155', bg: '#1e293b', text: '#64748b' },
    error: { border: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444' },
  };

  const colors = statusColors[data.status];
  return (
    <div
      className="rounded-xl border-2 p-4 min-w-[200px] cursor-pointer transition-all hover:shadow-lg"
      style={{ borderColor: colors.border, backgroundColor: colors.bg }}
      onClick={data.onToggle}
      role="button"
      tabIndex={0}
      aria-expanded={data.expanded}
    >
      <Handle type="target" position={Position.Top} style={{ background: colors.border }} />
      <div className="flex items-center gap-2 mb-2">
        {ICON_MAP[data.icon]}
        <span className="font-semibold text-sm" style={{ color: colors.text }}>{data.label}</span>
      </div>
      <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{data.description}</p>
      {data.expanded && (
        <div className="mt-2 pt-2 border-t" style={{ borderColor: 'var(--color-border)' }}>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{data.details}</p>
        </div>
      )}
      <div className="flex items-center gap-1 mt-1">
        <span className={`w-1.5 h-1.5 rounded-full`} style={{ backgroundColor: colors.text }} />
        <span className="text-xs capitalize" style={{ color: colors.text }}>{data.status}</span>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: colors.border }} />
    </div>
  );
}

export default function PipelineDebugger() {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);

  const { data: stats } = useQuery({
    queryKey: ['stats', 1],
    queryFn: () => api.stats(1),
  });

  const nodes: Node[] = useMemo(() => PIPELINE_STAGES.map((stage, i) => ({
    id: stage.id,
    type: 'custom',
    position: { x: 0, y: i * 160 },
    width: 200,
    height: expandedId === stage.id ? 150 : 110,
    data: {
      ...stage,
      status: stage.id === 'score' ? 'active' : stage.id === 'search' || stage.id === 'filter' ? 'completed' : 'pending',
      expanded: expandedId === stage.id,
      onToggle: () => setExpandedId(prev => prev === stage.id ? null : stage.id),
    },
  })), [expandedId]);

  const edges: Edge[] = useMemo(() => PIPELINE_STAGES.slice(0, -1).map((stage, i) => ({
    id: `e-${stage.id}-${PIPELINE_STAGES[i + 1].id}`,
    source: stage.id,
    target: PIPELINE_STAGES[i + 1].id,
    animated: true,
    style: { stroke: '#38bdf8', strokeWidth: 2 },
  })), []);

  const getMiniMapNodeColor = (node: Node) => {
    const status = node.data?.status as 'active' | 'completed' | 'pending' | 'error';
    switch (status) {
      case 'completed':
        return '#22c55e';
      case 'active':
        return '#38bdf8';
      case 'error':
        return '#ef4444';
      case 'pending':
      default:
        return '#475569';
    }
  };

  const nodeTypes = useMemo(() => ({ custom: PipelineNode }), []);
  const stageDetails = selectedStage && PIPELINE_STAGES.find(s => s.id === selectedStage);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>Visual Pipeline Debugger</h1>
        <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>Data-flow visualization of the agent's job application pipeline</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {PIPELINE_STAGES.map(stage => (
          <button
            key={stage.id}
            onClick={() => setSelectedStage(prev => prev === stage.id ? null : stage.id)}
            className="rounded-xl border p-4 text-left transition-all"
            style={{
              backgroundColor: selectedStage === stage.id ? 'rgba(56, 189, 248, 0.1)' : 'var(--color-surface)',
              borderColor: selectedStage === stage.id ? 'var(--color-primary)' : 'var(--color-border)',
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              {ICON_MAP[stage.icon]}
              <span className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>{stage.label}</span>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>{stage.description}</p>
          </button>
        ))}
      </div>

      {stageDetails && (
        <div className="rounded-xl border p-4" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {ICON_MAP[stageDetails.icon]}
              <h3 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>{stageDetails.label}</h3>
            </div>
            <button
              onClick={() => setSelectedStage(null)}
              className="text-xs px-2 py-1 rounded hover:bg-[#334155] transition-colors"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Close
            </button>
          </div>
          <p className="text-sm mt-2" style={{ color: 'var(--color-text-secondary)' }}>{stageDetails.details}</p>
          {stats && (
            <div className="mt-3 grid grid-cols-3 gap-3">
              <div className="p-3 rounded-lg" style={{ backgroundColor: 'var(--color-bg)' }}>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Jobs Found</p>
                <p className="text-lg font-bold" style={{ color: 'var(--color-text)' }}>{stats.total_jobs_found}</p>
              </div>
              <div className="p-3 rounded-lg" style={{ backgroundColor: 'var(--color-bg)' }}>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Applied</p>
                <p className="text-lg font-bold text-green-400">{stats.total_applied}</p>
              </div>
              <div className="p-3 rounded-lg" style={{ backgroundColor: 'var(--color-bg)' }}>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Success Rate</p>
                <p className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
                  {stats.total_applied > 0 ? `${Math.round((stats.total_applied / (stats.total_applied + stats.total_failed)) * 100)}%` : 'N/A'}
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="rounded-xl border" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)', height: 500 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#334155" gap={20} />
          <Controls />
          <MiniMap nodeColor={getMiniMapNodeColor} />
        </ReactFlow>
      </div>
    </div>
  );
}
