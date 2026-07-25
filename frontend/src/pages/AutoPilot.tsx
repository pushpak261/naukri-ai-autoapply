import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Zap, Bell, Clock, Shield, Plus, Trash2, ToggleLeft, ToggleRight,
  AlertCircle, CheckCircle, XCircle,
} from 'lucide-react';
import { api, type AutopilotConfig } from '../lib/api';
import { CardSkeleton } from '../components/Skeleton';

const DAYS = [
  { key: 'mon', label: 'Mon' },
  { key: 'tue', label: 'Tue' },
  { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' },
  { key: 'fri', label: 'Fri' },
  { key: 'sat', label: 'Sat' },
  { key: 'sun', label: 'Sun' },
];

type Notification = { type: 'success' | 'error' | 'info'; message: string };

export default function AutoPilot() {
  const queryClient = useQueryClient();
  const [notification, setNotification] = useState<Notification | null>(null);
  const [companyInput, setCompanyInput] = useState('');
  const [listType, setListType] = useState<'blacklist' | 'whitelist'>('blacklist');
  const [editing, setEditing] = useState(false);

  const { data: config, isLoading, isError } = useQuery({
    queryKey: ['autopilot', 'config'],
    queryFn: () => api.autopilot.config(),
  });

  const [localConfig, setLocalConfig] = useState<AutopilotConfig | null>(null);

  const displayConfig = editing ? localConfig : config;

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => api.autopilot.updateConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autopilot', 'config'] });
      setEditing(false);
      setNotification({ type: 'success', message: 'Auto-pilot configuration saved' });
    },
    onError: (err: Error) => setNotification({ type: 'error', message: `Failed to save: ${err.message}` }),
  });

  const addMutation = useMutation<any, Error, { company: string; list: string }>({
    mutationFn: ({ company, list }) =>
      list === 'whitelist' ? api.autopilot.addToWhitelist(company) : api.autopilot.addToBlacklist(company),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['autopilot', 'config'] });
      setCompanyInput('');
      setNotification({ type: 'success', message: `Added to ${variables.list}` });
    },
    onError: (err: Error) => setNotification({ type: 'error', message: err.message }),
  });

  const removeMutation = useMutation<any, Error, { company: string; list: string }>({
    mutationFn: ({ company, list }) =>
      list === 'whitelist' ? api.autopilot.removeFromWhitelist(company) : api.autopilot.removeFromBlacklist(company),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autopilot', 'config'] });
      setNotification({ type: 'info', message: 'Removed from list' });
    },
    onError: (err: Error) => setNotification({ type: 'error', message: err.message }),
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-8 w-48 bg-[#334155] rounded animate-pulse" />
          <div className="h-4 w-64 bg-[#334155] rounded animate-pulse mt-2" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <CardSkeleton key={i} />)}
        </div>
      </div>
    );
  }

  if (isError) {
    return <div className="text-red-400">Failed to load auto-pilot configuration.</div>;
  }

  const cfg = displayConfig ?? {
    enabled: false,
    schedule: { type: 'daily', time: '09:00', days: ['mon', 'tue', 'wed', 'thu', 'fri'] },
    throttle: { top_tier_daily: 3, startup_daily: 10, default_daily: 5 },
    priority_rules: [],
    company_blacklist: [],
    company_whitelist: [],
    tier_map: {},
  };

  const startEdit = () => {
    if (config) setLocalConfig(JSON.parse(JSON.stringify(config)));
    setEditing(true);
  };

  const toggleEnabled = () => {
    const next = !cfg.enabled;
    if (editing && localConfig) {
      setLocalConfig({ ...localConfig, enabled: next });
    } else {
      saveMutation.mutate({ enabled: next });
    }
  };

  const currentList = listType === 'blacklist' ? cfg.company_blacklist : cfg.company_whitelist;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--color-text)' }}>Strategic Auto-Pilot</h1>
          <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>Schedule runs, set priority rules, and manage company preferences</p>
        </div>
        <button
          onClick={toggleEnabled}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            cfg.enabled ? 'bg-green-600 text-white' : 'bg-[#334155] text-[#94a3b8]'
          }`}
          aria-label={cfg.enabled ? 'Disable auto-pilot' : 'Enable auto-pilot'}
        >
          {cfg.enabled ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
          {cfg.enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>

      {notification && (
        <div
          className={`flex items-center gap-3 px-4 py-3 rounded-lg border text-sm ${
            notification.type === 'success' ? 'bg-green-500/15 border-green-500/30 text-green-400'
            : notification.type === 'error' ? 'bg-red-500/15 border-red-500/30 text-red-400'
            : 'bg-blue-500/15 border-blue-500/30 text-blue-400'
          }`}
        >
          {notification.type === 'success' ? <CheckCircle className="w-4 h-4 shrink-0" />
            : notification.type === 'error' ? <XCircle className="w-4 h-4 shrink-0" />
            : <AlertCircle className="w-4 h-4 shrink-0" />}
          <span className="flex-1">{notification.message}</span>
          <button onClick={() => setNotification(null)} className="opacity-60 hover:opacity-100">&times;</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Clock className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />
            Schedule
          </h2>
          <div className="space-y-3">
            <div>
              <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Frequency</label>
              <select
                value={cfg.schedule.type}
                onChange={e => {
                  if (editing && localConfig) {
                    setLocalConfig({ ...localConfig, schedule: { ...localConfig.schedule, type: e.target.value } });
                  }
                }}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                disabled={!editing}
              >
                <option value="daily">Daily</option>
                <option value="weekdays">Weekdays Only</option>
                <option value="weekly">Weekly</option>
                <option value="custom">Custom Days</option>
              </select>
            </div>
            <div>
              <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Time</label>
              <input
                type="time"
                value={cfg.schedule.time}
                onChange={e => {
                  if (editing && localConfig) {
                    setLocalConfig({ ...localConfig, schedule: { ...localConfig.schedule, time: e.target.value } });
                  }
                }}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                disabled={!editing}
              />
            </div>
            <div>
              <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Days</label>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {DAYS.map(d => {
                  const active = cfg.schedule.days.includes(d.key);
                  return (
                    <button
                      key={d.key}
                      onClick={() => {
                        if (editing && localConfig) {
                          const days = active
                            ? localConfig.schedule.days.filter(k => k !== d.key)
                            : [...localConfig.schedule.days, d.key];
                          setLocalConfig({ ...localConfig, schedule: { ...localConfig.schedule, days } });
                        }
                      }}
                      className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                        active ? 'bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/30'
                        : 'bg-[#0f172a] text-[#64748b] border border-[#334155]'
                      }`}
                      disabled={!editing}
                      style={active ? { borderColor: 'var(--color-primary)' } : undefined}
                    >
                      {d.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Zap className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />
            Throttle Limits
          </h2>
          <div className="space-y-3">
            <div>
              <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Top-tier companies (daily)</label>
              <input
                type="number"
                value={cfg.throttle.top_tier_daily}
                onChange={e => {
                  if (editing && localConfig) {
                    setLocalConfig({ ...localConfig, throttle: { ...localConfig.throttle, top_tier_daily: +e.target.value } });
                  }
                }}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                disabled={!editing}
                min={0}
                max={50}
              />
            </div>
            <div>
              <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Startups (daily)</label>
              <input
                type="number"
                value={cfg.throttle.startup_daily}
                onChange={e => {
                  if (editing && localConfig) {
                    setLocalConfig({ ...localConfig, throttle: { ...localConfig.throttle, startup_daily: +e.target.value } });
                  }
                }}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                disabled={!editing}
                min={0}
                max={50}
              />
            </div>
            <div>
              <label className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Default (daily)</label>
              <input
                type="number"
                value={cfg.throttle.default_daily}
                onChange={e => {
                  if (editing && localConfig) {
                    setLocalConfig({ ...localConfig, throttle: { ...localConfig.throttle, default_daily: +e.target.value } });
                  }
                }}
                className="w-full mt-1 px-3 py-2 rounded-lg border text-sm"
                style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
                disabled={!editing}
                min={0}
                max={50}
              />
            </div>
          </div>
        </div>

        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
            <Bell className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />
            Priority Rules
          </h2>
          <div className="space-y-2 max-h-[200px] overflow-y-auto">
            {cfg.priority_rules.length > 0 ? cfg.priority_rules.map((rule, i) => (
              <div key={i} className="p-2 rounded-lg text-xs" style={{ backgroundColor: 'var(--color-bg)', border: '1px solid var(--color-border)' }}>
                <div className="flex items-center justify-between">
                  <span className="font-medium" style={{ color: rule.enabled ? 'var(--color-success)' : 'var(--color-text-muted)' }}>
                    {rule.enabled ? 'Active' : 'Inactive'}
                  </span>
                  <button
                    onClick={() => {
                      if (editing && localConfig) {
                        const rules = localConfig.priority_rules.map((r, ri) => ri === i ? { ...r, enabled: !r.enabled } : r);
                        setLocalConfig({ ...localConfig, priority_rules: rules });
                      }
                    }}
                    className="p-0.5"
                    disabled={!editing}
                  >
                    {rule.enabled ? <ToggleRight className="w-3 h-3 text-green-400" /> : <ToggleLeft className="w-3 h-3 text-[#64748b]" />}
                  </button>
                </div>
                <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>{rule.condition}</p>
                <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>→ {rule.action}</p>
              </div>
            )) : (
              <p className="text-sm text-center py-4" style={{ color: 'var(--color-text-muted)' }}>No priority rules defined</p>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
              <Shield className="w-4 h-4" style={{ color: 'var(--color-primary)' }} />
              Company Management
            </h2>
            <div className="flex bg-[#0f172a] rounded-lg border border-[#334155] p-0.5">
              <button
                onClick={() => setListType('blacklist')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${listType === 'blacklist' ? 'bg-red-500/10 text-red-400' : 'text-[#64748b]'}`}
              >
                Blacklist
              </button>
              <button
                onClick={() => setListType('whitelist')}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${listType === 'whitelist' ? 'bg-green-500/10 text-green-400' : 'text-[#64748b]'}`}
              >
                Whitelist
              </button>
            </div>
          </div>
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={companyInput}
              onChange={e => setCompanyInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && companyInput.trim()) {
                  addMutation.mutate({ company: companyInput.trim(), list: listType });
                }
              }}
              placeholder={`Add company to ${listType}...`}
              className="flex-1 px-3 py-2 rounded-lg border text-sm"
              style={{ backgroundColor: 'var(--color-bg)', borderColor: 'var(--color-border)', color: 'var(--color-text)' }}
              aria-label={`Company name to add to ${listType}`}
            />
            <button
              onClick={() => companyInput.trim() && addMutation.mutate({ company: companyInput.trim(), list: listType })}
              disabled={!companyInput.trim()}
              className="px-3 py-2 rounded-lg text-sm font-medium bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/30 hover:bg-[#38bdf8]/20 transition-colors disabled:opacity-50"
              aria-label={`Add to ${listType}`}
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
            {currentList.length > 0 ? currentList.map((company, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded-lg" style={{ backgroundColor: 'var(--color-bg)', border: '1px solid var(--color-border)' }}>
                <span className="text-sm" style={{ color: 'var(--color-text)' }}>{company}</span>
                <button
                  onClick={() => removeMutation.mutate({ company, list: listType })}
                  className="p-1 rounded hover:bg-red-500/10 text-[#64748b] hover:text-red-400 transition-colors"
                  aria-label={`Remove ${company}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )) : (
              <p className="text-sm text-center py-6" style={{ color: 'var(--color-text-muted)' }}>
                No companies in {listType} yet
              </p>
            )}
          </div>
        </div>

        <div className="rounded-xl border p-5 flex flex-col items-center justify-center" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <Zap className="w-12 h-12 mb-3" style={{ color: 'var(--color-primary)' }} />
          <h3 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>Auto-Pilot Status</h3>
          <div className={`flex items-center gap-2 mt-2 px-4 py-1.5 rounded-full text-sm font-medium ${
            cfg.enabled ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-[#0f172a] text-[#64748b] border border-[#334155]'
          }`}>
            <span className={`w-2 h-2 rounded-full ${cfg.enabled ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
            {cfg.enabled ? 'Active — Agent will run on schedule' : 'Inactive'}
          </div>
          {cfg.enabled && (
            <p className="text-xs mt-3" style={{ color: 'var(--color-text-muted)' }}>
              Next run: {cfg.schedule.time} on {cfg.schedule.days.slice(0, 3).join(', ')}
              {cfg.schedule.days.length > 3 ? ` +${cfg.schedule.days.length - 3} more` : ''}
            </p>
          )}
          <div className="flex gap-2 mt-4">
            {editing ? (
              <>
                <button
                  onClick={() => { setEditing(false); setLocalConfig(null); }}
                  className="px-4 py-2 rounded-lg text-sm font-medium border"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                >
                  Cancel
                </button>
                <button
                  onClick={() => localConfig && saveMutation.mutate(localConfig as unknown as Record<string, unknown>)}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-[#38bdf8] text-white hover:bg-[#38bdf8]/90 transition-colors"
                  disabled={saveMutation.isPending}
                >
                  {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                </button>
              </>
            ) : (
              <button
                onClick={startEdit}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-[#334155] hover:bg-[#475569] transition-colors"
                style={{ color: 'var(--color-text)' }}
              >
                Edit Configuration
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
