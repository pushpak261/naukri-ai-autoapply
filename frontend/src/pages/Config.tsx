import { useState, useEffect } from 'react';
import { Save, RotateCcw, AlertCircle, CheckCircle } from 'lucide-react';
import { api, type ConfigResponse } from '../lib/api';

interface ConfigForm {
  search_keywords: string;
  search_locations: string;
  experience_min: number;
  experience_max: number;
  salary_min: number;
  freshness: number;
  max_pages: number;
  sort_by: string;
  enable_heuristics: boolean;
  daily_cap: number;
  match_score_threshold: number;
  delay_between_applies_min: number;
  delay_between_applies_max: number;
  skip_external_apply: boolean;
  dry_run: boolean;
  answer_questions_with_pdf: boolean;
  use_gemini: boolean;
  enable_matching: boolean;
  ai_model: string;
  current_ctc: string;
  expected_ctc: string;
  notice_period: string;
  current_location: string;
  preferred_locations: string;
  total_experience: string;
}

function configToForm(config: ConfigResponse): ConfigForm {
  return {
    search_keywords: config.search.keywords.join(', '),
    search_locations: config.search.locations.join(', '),
    experience_min: config.search.experience_min,
    experience_max: config.search.experience_max,
    salary_min: config.search.salary_min,
    freshness: config.search.freshness,
    max_pages: config.search.max_pages,
    sort_by: config.search.sort_by,
    enable_heuristics: config.search.enable_heuristics,
    daily_cap: config.application.daily_cap,
    match_score_threshold: config.application.match_score_threshold,
    delay_between_applies_min: config.application.delay_between_applies_min,
    delay_between_applies_max: config.application.delay_between_applies_max,
    skip_external_apply: config.application.skip_external_apply,
    dry_run: config.application.dry_run,
    answer_questions_with_pdf: config.application.answer_questions_with_pdf,
    use_gemini: config.ai.use_gemini,
    enable_matching: config.ai.enable_matching,
    ai_model: config.ai.model,
    current_ctc: config.profile.current_ctc,
    expected_ctc: config.profile.expected_ctc,
    notice_period: config.profile.notice_period,
    current_location: config.profile.current_location,
    preferred_locations: config.profile.preferred_locations.join(', '),
    total_experience: config.profile.total_experience,
  };
}

export default function Config() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.config().then((c) => {
      setConfig(c);
      setForm(configToForm(c));
    }).finally(() => setLoading(false));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setMessage(null);
    try {
      const payload: Record<string, unknown> = {
        search_keywords: form.search_keywords.split(',').map((s: string) => s.trim()).filter(Boolean),
        search_locations: form.search_locations.split(',').map((s: string) => s.trim()).filter(Boolean),
        experience_min: form.experience_min,
        experience_max: form.experience_max,
        salary_min: form.salary_min,
        freshness: form.freshness,
        max_pages: form.max_pages,
        sort_by: form.sort_by,
        enable_heuristics: form.enable_heuristics,
        daily_cap: form.daily_cap,
        match_score_threshold: form.match_score_threshold,
        delay_between_applies_min: form.delay_between_applies_min,
        delay_between_applies_max: form.delay_between_applies_max,
        skip_external_apply: form.skip_external_apply,
        dry_run: form.dry_run,
        answer_questions_with_pdf: form.answer_questions_with_pdf,
        use_gemini: form.use_gemini,
        enable_matching: form.enable_matching,
        ai_model: form.ai_model,
        current_ctc: form.current_ctc,
        expected_ctc: form.expected_ctc,
        notice_period: form.notice_period,
        current_location: form.current_location,
        preferred_locations: form.preferred_locations.split(',').map((s: string) => s.trim()).filter(Boolean),
        total_experience: form.total_experience,
      };
      await api.updateConfig(payload);
      setMessage({ type: 'success', text: 'Configuration saved successfully!' });
      const fresh = await api.config();
      setConfig(fresh);
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' });
    } finally {
      setSaving(false);
    }
  };

  const resetForm = () => {
    if (config) setForm(configToForm(config));
    setMessage(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (!form) return <div className="text-red-400">Failed to load configuration</div>;

  const inputClass = "w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm text-text placeholder:text-muted focus:outline-none focus:border-primary transition-colors";
  const labelClass = "block text-xs font-medium text-secondary mb-1.5";
  const sectionClass = "bg-surface rounded-xl border border-border p-5";

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">Configuration</h1>
          <p className="text-secondary mt-1">Manage agent settings</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={resetForm}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm text-secondary hover:bg-surface-hover transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            Reset
          </button>
        </div>
      </div>

      {message && (
        <div className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
          message.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          {message.text}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-text mb-4">Search Settings</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className={labelClass}>Keywords (comma-separated)</label>
              <input type="text" value={form.search_keywords} onChange={(e) => setForm({ ...form, search_keywords: e.target.value })} className={inputClass} placeholder="Full Stack Developer, Java Developer..." />
            </div>
            <div className="md:col-span-2">
              <label className={labelClass}>Locations (comma-separated)</label>
              <input type="text" value={form.search_locations} onChange={(e) => setForm({ ...form, search_locations: e.target.value })} className={inputClass} placeholder="Pune, Mumbai, Bangalore..." />
            </div>
            <div>
              <label className={labelClass}>Experience Min (years)</label>
              <input type="number" value={form.experience_min} onChange={(e) => setForm({ ...form, experience_min: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Experience Max (years)</label>
              <input type="number" value={form.experience_max} onChange={(e) => setForm({ ...form, experience_max: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Salary Min (LPA)</label>
              <input type="number" value={form.salary_min} onChange={(e) => setForm({ ...form, salary_min: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Freshness (days)</label>
              <input type="number" value={form.freshness} onChange={(e) => setForm({ ...form, freshness: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Max Pages</label>
              <input type="number" value={form.max_pages} onChange={(e) => setForm({ ...form, max_pages: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Sort By</label>
              <select value={form.sort_by} onChange={(e) => setForm({ ...form, sort_by: e.target.value })} className={inputClass}>
                <option value="relevance">Relevance</option>
                <option value="date">Date</option>
              </select>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="enable_heuristics" checked={form.enable_heuristics} onChange={(e) => setForm({ ...form, enable_heuristics: e.target.checked })} className="w-4 h-4 rounded border-border bg-bg text-primary focus:ring-[#38bdf8]" />
              <label htmlFor="enable_heuristics" className="text-sm text-secondary">Enable Heuristics (priority ranking)</label>
            </div>
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-text mb-4">Application Settings</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Daily Cap</label>
              <input type="number" value={form.daily_cap} onChange={(e) => setForm({ ...form, daily_cap: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Match Score Threshold</label>
              <input type="number" value={form.match_score_threshold} onChange={(e) => setForm({ ...form, match_score_threshold: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Delay Min (seconds)</label>
              <input type="number" value={form.delay_between_applies_min} onChange={(e) => setForm({ ...form, delay_between_applies_min: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Delay Max (seconds)</label>
              <input type="number" value={form.delay_between_applies_max} onChange={(e) => setForm({ ...form, delay_between_applies_max: Number(e.target.value) })} className={inputClass} />
            </div>
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <input type="checkbox" id="skip_external" checked={form.skip_external_apply} onChange={(e) => setForm({ ...form, skip_external_apply: e.target.checked })} className="w-4 h-4 rounded border-border bg-bg text-primary focus:ring-[#38bdf8]" />
                <label htmlFor="skip_external" className="text-sm text-secondary">Skip External Apply</label>
              </div>
              <div className="flex items-center gap-3">
                <input type="checkbox" id="dry_run" checked={form.dry_run} onChange={(e) => setForm({ ...form, dry_run: e.target.checked })} className="w-4 h-4 rounded border-border bg-bg text-primary focus:ring-[#38bdf8]" />
                <label htmlFor="dry_run" className="text-sm text-secondary">Dry Run (score only, no apply)</label>
              </div>
              <div className="flex items-center gap-3">
                <input type="checkbox" id="answer_pdf" checked={form.answer_questions_with_pdf} onChange={(e) => setForm({ ...form, answer_questions_with_pdf: e.target.checked })} className="w-4 h-4 rounded border-border bg-bg text-primary focus:ring-[#38bdf8]" />
                <label htmlFor="answer_pdf" className="text-sm text-secondary">Answer Questions with PDF</label>
              </div>
            </div>
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-text mb-4">AI Settings</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <input type="checkbox" id="use_gemini" checked={form.use_gemini} onChange={(e) => setForm({ ...form, use_gemini: e.target.checked })} className="w-4 h-4 rounded border-border bg-bg text-primary focus:ring-[#38bdf8]" />
              <label htmlFor="use_gemini" className="text-sm text-secondary">Use Gemini AI</label>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="enable_matching" checked={form.enable_matching} onChange={(e) => setForm({ ...form, enable_matching: e.target.checked })} className="w-4 h-4 rounded border-border bg-bg text-primary focus:ring-[#38bdf8]" />
              <label htmlFor="enable_matching" className="text-sm text-secondary">Enable AI Matching</label>
            </div>
            <div className="md:col-span-2">
              <label className={labelClass}>AI Model</label>
              <input type="text" value={form.ai_model} onChange={(e) => setForm({ ...form, ai_model: e.target.value })} className={inputClass} placeholder="gemini-2.5-flash" />
            </div>
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-text mb-4">Profile Settings</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Current CTC</label>
              <input type="text" value={form.current_ctc} onChange={(e) => setForm({ ...form, current_ctc: e.target.value })} className={inputClass} placeholder="4.4 LPA" />
            </div>
            <div>
              <label className={labelClass}>Expected CTC</label>
              <input type="text" value={form.expected_ctc} onChange={(e) => setForm({ ...form, expected_ctc: e.target.value })} className={inputClass} placeholder="6 LPA" />
            </div>
            <div>
              <label className={labelClass}>Notice Period</label>
              <input type="text" value={form.notice_period} onChange={(e) => setForm({ ...form, notice_period: e.target.value })} className={inputClass} placeholder="Immediate" />
            </div>
            <div>
              <label className={labelClass}>Current Location</label>
              <input type="text" value={form.current_location} onChange={(e) => setForm({ ...form, current_location: e.target.value })} className={inputClass} placeholder="Pune" />
            </div>
            <div>
              <label className={labelClass}>Total Experience</label>
              <input type="text" value={form.total_experience} onChange={(e) => setForm({ ...form, total_experience: e.target.value })} className={inputClass} placeholder="1 years" />
            </div>
            <div className="md:col-span-2">
              <label className={labelClass}>Preferred Locations (comma-separated)</label>
              <input type="text" value={form.preferred_locations} onChange={(e) => setForm({ ...form, preferred_locations: e.target.value })} className={inputClass} placeholder="Pune, Mumbai, Bangalore, Remote" />
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 bg-primary text-on-primary rounded-lg font-medium text-sm hover:bg-primary-hover disabled:opacity-50 transition-colors"
          >
            {saving ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-on-primary" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </form>
    </div>
  );
}
