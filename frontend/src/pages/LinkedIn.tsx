import { useState, useEffect, useCallback } from 'react';
import { Globe, Settings, Bot, Key, AlertCircle, CheckCircle, RefreshCw, Loader2 } from 'lucide-react';
import { api, type LinkedInConfig } from '../lib/api';

export default function LinkedIn() {
  const [config, setConfig] = useState<LinkedInConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [keywords, setKeywords] = useState('');
  const [locations, setLocations] = useState('');
  const [workType, setWorkType] = useState('');
  const [freshness, setFreshness] = useState('past_week');
  const [maxPages, setMaxPages] = useState(25);
  const [dailyCap, setDailyCap] = useState(150);
  const [matchThreshold, setMatchThreshold] = useState(40);
  const [dryRun, setDryRun] = useState(false);
  const [easyApplyOnly, setEasyApplyOnly] = useState(true);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const c = await api.linkedinConfig.get();
      setConfig(c);
      setKeywords(c.search.keywords.join(', '));
      setLocations(c.search.locations.join(', '));
      setWorkType(c.search.work_type);
      setFreshness(c.search.freshness);
      setMaxPages(c.search.max_pages);
      setDailyCap(c.application.daily_cap);
      setMatchThreshold(c.application.match_score_threshold);
      setDryRun(c.application.dry_run);
      setEasyApplyOnly(c.application.easy_apply_only);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to load config' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const handleSaveCredentials = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const data: Record<string, unknown> = {};
      if (email) data.linkedin_email = email;
      if (password) data.linkedin_password = password;
      await api.linkedinConfig.update(data);
      setMessage({ type: 'success', text: 'Credentials saved' });
      setPassword('');
      await fetchConfig();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' });
    }
    setSaving(false);
  };

  const handleSaveSearch = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await api.linkedinConfig.update({
        search_keywords: keywords.split(',').map(s => s.trim()).filter(Boolean),
        search_locations: locations.split(',').map(s => s.trim()).filter(Boolean),
        work_type: workType,
        freshness,
        max_pages: maxPages,
        daily_cap: dailyCap,
        match_score_threshold: matchThreshold,
        dry_run: dryRun,
        easy_apply_only: easyApplyOnly,
      });
      setMessage({ type: 'success', text: 'Search configuration saved' });
      await fetchConfig();
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' });
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#0077b5]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2" style={{ color: 'var(--color-text)' }}>
          <Globe className="w-6 h-6 text-[#0077b5]" />
          LinkedIn Agent
        </h1>
        <p className="mt-1" style={{ color: 'var(--color-text-secondary)' }}>Configure and manage the LinkedIn job application agent</p>
      </div>

      {message && (
        <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
          message.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          {message.text}
          <button onClick={() => setMessage(null)} className="ml-auto text-current opacity-60 hover:opacity-100">&times;</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Credentials */}
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
            <Key className="w-4 h-4" />
            Authentication
            {config?.configured && (
              <span className="ml-auto flex items-center gap-1 text-xs text-green-400">
                <CheckCircle className="w-3 h-3" />
                Configured
              </span>
            )}
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Email {config?.email && <span className="text-[#64748b]">(current: {config.email})</span>}
              </label>
              <input
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748b] focus:outline-none focus:border-[#0077b5] transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                Password {config?.has_password && <span className="text-green-400">(set)</span>}
              </label>
              <input
                type="password"
                placeholder={config?.has_password ? '•••••••• (leave blank to keep)' : 'Enter password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748b] focus:outline-none focus:border-[#0077b5] transition-colors"
              />
            </div>
            <button
              onClick={handleSaveCredentials}
              disabled={saving}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-[#0077b5] hover:bg-[#005e93] text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Save Credentials
            </button>
          </div>
        </div>

        {/* Agent Status */}
        <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
          <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
            <Bot className="w-4 h-4" />
            Agent Capabilities
          </h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
              <span className="text-sm" style={{ color: 'var(--color-text)' }}>LinkedIn Module</span>
              <span className="flex items-center gap-1.5 text-xs text-green-400">
                <CheckCircle className="w-3.5 h-3.5" />
                Available
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
              <span className="text-sm" style={{ color: 'var(--color-text)' }}>Easy Apply Support</span>
              <span className="flex items-center gap-1.5 text-xs text-green-400">
                <CheckCircle className="w-3.5 h-3.5" />
                Enabled
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
              <span className="text-sm" style={{ color: 'var(--color-text)' }}>Anti-Bot Stealth</span>
              <span className="flex items-center gap-1.5 text-xs text-green-400">
                <CheckCircle className="w-3.5 h-3.5" />
                Active (14 patches)
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
              <span className="text-sm" style={{ color: 'var(--color-text)' }}>AI Matching</span>
              <span className={`flex items-center gap-1.5 text-xs ${config?.ai.enable_matching ? 'text-green-400' : 'text-[#64748b]'}`}>
                {config?.ai.enable_matching ? <CheckCircle className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                {config?.ai.enable_matching ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-[#0f172a] border border-[#334155]">
              <span className="text-sm" style={{ color: 'var(--color-text)' }}>Resume</span>
              <span className={`flex items-center gap-1.5 text-xs ${config?.resume.exists ? 'text-green-400' : 'text-yellow-400'}`}>
                {config?.resume.exists ? <CheckCircle className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                {config?.resume.exists ? config.resume.path : 'Not found'}
              </span>
            </div>
          </div>

          <div className="mt-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-yellow-400 mt-0.5 shrink-0" />
              <p className="text-xs text-yellow-300">
                LinkedIn has stricter anti-bot detection. Configure credentials above, set up search keywords, then start from <strong>Agent Control</strong> with the LinkedIn platform selected.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Search Configuration */}
      <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
        <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: 'var(--color-text-secondary)' }}>
          <Settings className="w-4 h-4" />
          Search & Application Settings
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Keywords (comma-separated)</label>
            <input
              type="text"
              placeholder="python developer, react engineer"
              value={keywords}
              onChange={e => setKeywords(e.target.value)}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748b] focus:outline-none focus:border-[#0077b5] transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Locations (comma-separated)</label>
            <input
              type="text"
              placeholder="Bangalore, Mumbai, Remote"
              value={locations}
              onChange={e => setLocations(e.target.value)}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white placeholder-[#64748b] focus:outline-none focus:border-[#0077b5] transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Work Type</label>
            <select
              value={workType}
              onChange={e => setWorkType(e.target.value)}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-[#94a3b8] focus:outline-none focus:border-[#0077b5] transition-colors"
            >
              <option value="">Any</option>
              <option value="remote">Remote</option>
              <option value="on_site">On-site</option>
              <option value="hybrid">Hybrid</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Freshness</label>
            <select
              value={freshness}
              onChange={e => setFreshness(e.target.value)}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-[#94a3b8] focus:outline-none focus:border-[#0077b5] transition-colors"
            >
              <option value="past_week">Past Week</option>
              <option value="past_24h">Past 24 Hours</option>
              <option value="past_month">Past Month</option>
              <option value="any">Any Time</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Max Pages</label>
            <input
              type="number"
              min={1}
              max={50}
              value={maxPages}
              onChange={e => setMaxPages(Number(e.target.value))}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#0077b5] transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Daily Cap</label>
            <input
              type="number"
              min={1}
              max={500}
              value={dailyCap}
              onChange={e => setDailyCap(Number(e.target.value))}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#0077b5] transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Match Score Threshold (%)</label>
            <input
              type="number"
              min={0}
              max={100}
              value={matchThreshold}
              onChange={e => setMatchThreshold(Number(e.target.value))}
              className="w-full bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#0077b5] transition-colors"
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={e => setDryRun(e.target.checked)}
                className="w-4 h-4 rounded border-[#334155] bg-[#0f172a] text-[#0077b5] focus:ring-[#0077b5]"
              />
              <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>Dry Run</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={easyApplyOnly}
                onChange={e => setEasyApplyOnly(e.target.checked)}
                className="w-4 h-4 rounded border-[#334155] bg-[#0f172a] text-[#0077b5] focus:ring-[#0077b5]"
              />
              <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>Easy Apply Only</span>
            </label>
          </div>
        </div>
        <div className="mt-4">
          <button
            onClick={handleSaveSearch}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-[#0077b5] hover:bg-[#005e93] text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            Save Configuration
          </button>
        </div>
      </div>

      {/* Quick Start Guide */}
      <div className="rounded-xl border p-5" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
        <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>Quick Start</h2>
        <ol className="space-y-2 text-sm" style={{ color: 'var(--color-text)' }}>
          <li className="flex items-start gap-2">
            <span className="flex items-center justify-center w-5 h-5 rounded-full bg-[#0077b5]/20 text-[#0077b5] text-xs font-bold shrink-0 mt-0.5">1</span>
            <span>Enter your LinkedIn email and password above, click <strong>Save Credentials</strong></span>
          </li>
          <li className="flex items-start gap-2">
            <span className="flex items-center justify-center w-5 h-5 rounded-full bg-[#0077b5]/20 text-[#0077b5] text-xs font-bold shrink-0 mt-0.5">2</span>
            <span>Set your search keywords (e.g. "python developer") and locations, click <strong>Save Configuration</strong></span>
          </li>
          <li className="flex items-start gap-2">
            <span className="flex items-center justify-center w-5 h-5 rounded-full bg-[#0077b5]/20 text-[#0077b5] text-xs font-bold shrink-0 mt-0.5">3</span>
            <span>Go to <strong>Agent Control</strong>, select the <strong>LinkedIn</strong> platform tab, and click <strong>Start</strong></span>
          </li>
          <li className="flex items-start gap-2">
            <span className="flex items-center justify-center w-5 h-5 rounded-full bg-[#0077b5]/20 text-[#0077b5] text-xs font-bold shrink-0 mt-0.5">4</span>
            <span>Monitor progress in the Live Output log. Jobs are saved to <strong>Jobs</strong> and <strong>Applications</strong> pages with LinkedIn badges</span>
          </li>
        </ol>
      </div>
    </div>
  );
}
