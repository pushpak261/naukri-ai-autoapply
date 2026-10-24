import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Save, RotateCcw, AlertCircle, CheckCircle, Bell, Gauge } from 'lucide-react';
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
  current_city: string;
  current_state: string;
  current_country: string;
  preferred_locations: string;
  total_experience: string;
  employment_status: string;
  serving_notice: string;
  last_working_date: string;
  confirmed_answers: {question: string; answer: string}[];
  skill_experience: {skill: string; years: string}[];
  max_retries: number;
  email_notifications_enabled: boolean;
  notify_on_apply: boolean;
  notify_on_failure: boolean;
  notify_on_scam: boolean;
  notify_on_match: boolean;
  rate_limit_capacity: number;
  rate_limit_refill_rate: number;
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
    current_city: config.profile.current_city ?? config.profile.current_location,
    current_state: config.profile.current_state ?? '',
    current_country: config.profile.current_country ?? '',
    preferred_locations: config.profile.preferred_locations.join(', '),
    total_experience: config.profile.total_experience,
    employment_status: config.profile.employment_status ?? '',
    serving_notice: config.profile.serving_notice == null ? '' : String(config.profile.serving_notice),
    last_working_date: config.profile.last_working_date ?? '',
    confirmed_answers: Object.entries(config.profile.confirmed_answers ?? {}).map(([question, answer]) => ({question, answer})),
    skill_experience: Object.entries(config.profile.skill_experience_years ?? {}).map(([skill, years]) => ({skill, years: String(years)})),
    max_retries: config.application.max_retries ?? 3,
    email_notifications_enabled: config.notifications?.email_notifications_enabled ?? false,
    notify_on_apply: config.notifications?.notify_on_apply ?? true,
    notify_on_failure: config.notifications?.notify_on_failure ?? true,
    notify_on_scam: config.notifications?.notify_on_scam ?? true,
    notify_on_match: config.notifications?.notify_on_match ?? false,
    rate_limit_capacity: config.rate_limits?.rate_limit_capacity ?? 10,
    rate_limit_refill_rate: config.rate_limits?.rate_limit_refill_rate ?? 1,
  };
}

export default function Config() {
  const queryClient = useQueryClient();
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [aiKey, setAIKey] = useState('');
  const [testingAI, setTestingAI] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.config().then((c) => {
      if (!active) return;
      setConfig(c);
      setForm(configToForm(c));
    }).catch(error => {
      if (active) setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to load preferences' });
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loadAttempt]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form || savingKey || testingAI || saving) return;
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
        max_retries: form.max_retries,
        current_ctc: form.current_ctc,
        expected_ctc: form.expected_ctc,
        notice_period: form.notice_period,
        current_location: form.current_location,
        current_city: form.current_city,
        current_state: form.current_state,
        current_country: form.current_country,
        preferred_locations: form.preferred_locations.split(',').map((s: string) => s.trim()).filter(Boolean),
        total_experience: form.total_experience,
        employment_status: form.employment_status,
        serving_notice: form.serving_notice === '' ? null : form.serving_notice === 'true',
        last_working_date: form.last_working_date,
        confirmed_answers: Object.fromEntries(form.confirmed_answers.filter(row => row.question.trim() && row.answer.trim()).map(row => [row.question.trim(), row.answer.trim()])),
        skill_experience_years: Object.fromEntries(form.skill_experience.filter(row => row.skill.trim() && row.years.trim()).map(row => [row.skill.trim(), Number(row.years)])),
        email_notifications_enabled: form.email_notifications_enabled,
        notify_on_apply: form.notify_on_apply,
        notify_on_failure: form.notify_on_failure,
        notify_on_scam: form.notify_on_scam,
        notify_on_match: form.notify_on_match,
        rate_limit_capacity: form.rate_limit_capacity,
        rate_limit_refill_rate: form.rate_limit_refill_rate,
      };
      if (aiKey.trim()) payload.gemini_api_key = aiKey.trim();
      await api.updateConfig(payload);
      setAIKey('');
      setMessage({ type: 'success', text: 'Configuration saved successfully!' });
      const fresh = await api.config();
      setConfig(fresh);
      setForm(configToForm(fresh));
      queryClient.setQueryData(['config'], fresh);
      await queryClient.invalidateQueries({ queryKey: ['stats'] });
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save' });
    } finally {
      setSaving(false);
    }
  };

  const saveGeminiKey = async () => {
    if (!form || !aiKey.trim() || savingKey || saving) return;
    setSavingKey(true);
    setMessage(null);
    try {
      await api.updateConfig({ gemini_api_key: aiKey.trim(), use_gemini: true, enable_matching: true, ai_model: form.ai_model.trim() || 'gemini-2.5-flash' });
      setAIKey('');
      const fresh = await api.config();
      setConfig(fresh);
      setForm(current => current ? { ...current, use_gemini: fresh.ai.use_gemini, enable_matching: fresh.ai.enable_matching, ai_model: fresh.ai.model } : current);
      queryClient.setQueryData(['config'], fresh);
      setMessage({ type: 'success', text: 'Gemini API key saved. Click Test saved AI connection to verify it.' });
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Failed to save Gemini key' });
    } finally {
      setSavingKey(false);
    }
  };

  const resetForm = () => {
    if (config) setForm(configToForm(config));
    setMessage(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
      </div>
    );
  }

  if (!form) return <div role="alert" className="notice-error"><p>{message?.text || 'Failed to load configuration'}</p><button className="secondary-button" onClick={() => setLoadAttempt(value => value + 1)}>Retry preferences</button></div>;

  const inputClass = "w-full bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] placeholder-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)] transition-colors";
  const labelClass = "block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5";
  const sectionClass = "bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5";

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text)]">Configuration</h1>
          <p className="text-[var(--color-text-secondary)] mt-1">Manage agent settings</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={resetForm}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--color-border)] text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
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
        <div id="ai-settings" className={sectionClass}>
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4">Gemini AI Settings</h2>
          <p className="text-sm mb-3 text-[var(--color-text-secondary)]">Shared by Naukri and LinkedIn. Save your key before testing. Existing statistics and evidence scores remain data-based.</p>
          <label className={labelClass} htmlFor="gemini-key">Gemini API key {config?.ai.has_api_key ? '(saved)' : '(required for AI)'}</label>
          <input id="gemini-key" type="password" autoComplete="new-password" value={aiKey} onChange={e => { setAIKey(e.target.value); if (e.target.value.trim()) setForm({ ...form, use_gemini: true }); }} className={inputClass} disabled={savingKey || saving || testingAI} placeholder={config?.ai.has_api_key ? "Leave blank to keep the saved key" : "Paste your Gemini API key here"} />
          <button type="button" className="primary-button my-3 mr-3" disabled={!aiKey.trim() || savingKey || saving || testingAI} onClick={saveGeminiKey}>{savingKey ? 'Saving key…' : 'Save Gemini key'}</button>
          <button type="button" className="secondary-button my-3" disabled={testingAI || saving || savingKey || !!aiKey || !config?.ai.has_api_key} onClick={async () => { setTestingAI(true); try { const r = await api.testAI(); setMessage({type:'success', text:r.message + ' Model: ' + r.model}); } catch (e) { setMessage({type:'error',text:e instanceof Error ? e.message : 'AI test failed'}); } finally { setTestingAI(false); } }}>{testingAI ? 'Testing AIâ€¦' : 'Test saved AI connection'}</button>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <input type="checkbox" id="use_gemini" checked={form.use_gemini} onChange={(e) => setForm({ ...form, use_gemini: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)] focus:ring-[#38bdf8]" />
              <label htmlFor="use_gemini" className="text-sm text-[var(--color-text-secondary)]">Use Gemini AI</label>
            </div>
            <div className="flex items-center gap-3">
              <input type="checkbox" id="enable_matching" checked={form.enable_matching} onChange={(e) => setForm({ ...form, enable_matching: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)] focus:ring-[#38bdf8]" />
              <label htmlFor="enable_matching" className="text-sm text-[var(--color-text-secondary)]">Enable AI Matching</label>
            </div>
            <div className="md:col-span-2">
              <label className={labelClass}>AI Model</label>
              <input type="text" value={form.ai_model} onChange={(e) => setForm({ ...form, ai_model: e.target.value })} className={inputClass} placeholder="gemini-2.5-flash" />
            </div>
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4">Search Settings</h2>
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
              <input type="checkbox" id="enable_heuristics" checked={form.enable_heuristics} onChange={(e) => setForm({ ...form, enable_heuristics: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)] focus:ring-[#38bdf8]" />
              <label htmlFor="enable_heuristics" className="text-sm text-[var(--color-text-secondary)]">Enable Heuristics (priority ranking)</label>
            </div>
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4">Application Settings</h2>
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
              <label className={labelClass}>Max Retries (per failure)</label>
              <input type="number" min="0" value={form.max_retries} onChange={(e) => setForm({ ...form, max_retries: Number(e.target.value) })} className={inputClass} />
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
                <input type="checkbox" id="external_apply" checked={!form.skip_external_apply} onChange={(e) => setForm({ ...form, skip_external_apply: !e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)]" />
                <label htmlFor="external_apply" className="text-sm text-[var(--color-text-secondary)]">Apply on external employer websites with Gemini</label>
              </div>
              <p className="text-xs muted">Requires a saved Gemini API key, even when Gemini is off for native applications. Sends your saved application profile and form labels to Gemini, and completed answers and resume to the employer. Required unknown answers appear in Screening answers. Login, CAPTCHA and legal agreements need your direct review. Only confirmed submissions count as applied.</p>
              <div className="flex items-center gap-3">
                <input type="checkbox" id="dry_run" checked={form.dry_run} onChange={(e) => setForm({ ...form, dry_run: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)] focus:ring-[#38bdf8]" />
                <label htmlFor="dry_run" className="text-sm text-[var(--color-text-secondary)]">Dry Run (score only, no apply)</label>
              </div>
              <div className="flex items-center gap-3">
                <input type="checkbox" id="answer_pdf" checked={form.answer_questions_with_pdf} onChange={(e) => setForm({ ...form, answer_questions_with_pdf: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)] focus:ring-[#38bdf8]" />
                <label htmlFor="answer_pdf" className="text-sm text-[var(--color-text-secondary)]">Fill screening questions from resume and saved facts</label>
              </div>
            </div>
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold mb-2">Gemini-free application assistant</h2>
          <p className="text-sm muted mb-4">With Use Gemini AI off, Naukri answers from saved facts, resume summaries and local technical answers. Missing facts appear under Applications → Screening answers. Confirm them once and retry without submitting empty answers. No AI API key is needed.</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
            <div><label htmlFor="employment-status" className={labelClass}>Employment status</label>
              <select id="employment-status" className={inputClass} value={form.employment_status} onChange={e => setForm({...form, employment_status: e.target.value})}>
                <option value="">Not confirmed</option><option value="employed">Employed</option><option value="unemployed">Not employed</option><option value="student">Student</option>
              </select></div>
            <div><label htmlFor="serving-notice" className={labelClass}>Serving notice now?</label>
              <select id="serving-notice" className={inputClass} value={form.serving_notice} onChange={e => setForm({...form, serving_notice: e.target.value})}>
                <option value="">Not confirmed</option><option value="true">Yes</option><option value="false">No</option>
              </select></div>
            <div><label htmlFor="last-working-date" className={labelClass}>Confirmed last working date</label>
              <input id="last-working-date" type="date" className={inputClass} value={form.last_working_date} onChange={e => setForm({...form, last_working_date: e.target.value})}/>
              <p className="text-xs muted mt-1">Leave unset if no date has been agreed.</p></div>
          </div>
          <h3 className="font-medium mb-2">Confirmed screening answers</h3>
          <p className="text-sm muted mb-3">Enter the exact question and your truthful answer. For choices, use the exact option text. Save only answers that apply whenever that same question appears.</p>
          {form.confirmed_answers.map((row, index) => <div key={index} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-2 mb-2">
            <input aria-label={`Screening question ${index + 1}`} placeholder="Exact screening question" value={row.question} maxLength={300} className={inputClass} onChange={e => setForm({...form, confirmed_answers: form.confirmed_answers.map((r,i) => i === index ? {...r, question: e.target.value} : r)})}/>
            <input aria-label={`Confirmed answer ${index + 1}`} placeholder="Your confirmed answer" value={row.answer} maxLength={1000} className={inputClass} onChange={e => setForm({...form, confirmed_answers: form.confirmed_answers.map((r,i) => i === index ? {...r, answer: e.target.value} : r)})}/>
            <button type="button" className="secondary-button" aria-label={`Remove answer ${index + 1}`} onClick={() => setForm({...form, confirmed_answers: form.confirmed_answers.filter((_,i) => i !== index)})}>Remove</button>
          </div>)}
          <button type="button" className="secondary-button mb-5" onClick={() => setForm({...form, confirmed_answers: [...form.confirmed_answers, {question: '', answer: ''}]})}>Add confirmed answer</button>
          <h3 className="font-medium mb-2">Experience by skill</h3>
          <p className="text-sm muted mb-3">Enter actual professional experience in years. Listing a skill in your resume does not establish how long you used it.</p>
          {form.skill_experience.map((row, index) => <div key={index} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-2 mb-2">
            <input aria-label={`Skill ${index + 1}`} placeholder="Skill" value={row.skill} className={inputClass} onChange={e => setForm({...form, skill_experience: form.skill_experience.map((r,i) => i === index ? {...r, skill: e.target.value} : r)})}/>
            <input type="number" min="0" max="80" step="0.1" aria-label={`Years using skill ${index + 1}`} placeholder="Years" value={row.years} className={inputClass} onChange={e => setForm({...form, skill_experience: form.skill_experience.map((r,i) => i === index ? {...r, years: e.target.value} : r)})}/>
            <button type="button" className="secondary-button" aria-label={`Remove skill ${index + 1}`} onClick={() => setForm({...form, skill_experience: form.skill_experience.filter((_,i) => i !== index)})}>Remove</button>
          </div>)}
          <button type="button" className="secondary-button" onClick={() => setForm({...form, skill_experience: [...form.skill_experience, {skill: '', years: ''}]})}>Add skill experience</button>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4">Profile Settings</h2>
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
              <label htmlFor="current-city" className={labelClass}>Current city</label>
              <input id="current-city" type="text" value={form.current_city} onChange={(e) => setForm({ ...form, current_location: e.target.value, current_city: e.target.value })} className={inputClass} placeholder="Pune" />
            </div>
            <div>
              <label htmlFor="current-state" className={labelClass}>State / province</label>
              <input id="current-state" type="text" value={form.current_state} onChange={(e) => setForm({ ...form, current_state: e.target.value })} className={inputClass} placeholder="Maharashtra" />
            </div>
            <div>
              <label htmlFor="current-country" className={labelClass}>Country of residence</label>
              <input id="current-country" type="text" value={form.current_country} onChange={(e) => setForm({ ...form, current_country: e.target.value })} className={inputClass} placeholder="India" />
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

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
            <Bell className="w-5 h-5 text-[var(--color-primary)]" />
            Notification Settings
          </h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <input type="checkbox" id="email_notifications" checked={form.email_notifications_enabled} onChange={(e) => setForm({ ...form, email_notifications_enabled: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)] focus:ring-[#38bdf8]" />
              <label htmlFor="email_notifications" className="text-sm text-[var(--color-text-secondary)]">Enable Email Notifications</label>
            </div>
            {form.email_notifications_enabled && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pl-6">
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="notify_apply" checked={form.notify_on_apply} onChange={(e) => setForm({ ...form, notify_on_apply: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)]" />
                  <label htmlFor="notify_apply" className="text-xs text-[var(--color-text-secondary)]">On Apply</label>
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="notify_failure" checked={form.notify_on_failure} onChange={(e) => setForm({ ...form, notify_on_failure: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)]" />
                  <label htmlFor="notify_failure" className="text-xs text-[var(--color-text-secondary)]">On Failure</label>
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="notify_scam" checked={form.notify_on_scam} onChange={(e) => setForm({ ...form, notify_on_scam: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)]" />
                  <label htmlFor="notify_scam" className="text-xs text-[var(--color-text-secondary)]">On Scam</label>
                </div>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="notify_match" checked={form.notify_on_match} onChange={(e) => setForm({ ...form, notify_on_match: e.target.checked })} className="w-4 h-4 rounded border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-primary)]" />
                  <label htmlFor="notify_match" className="text-xs text-[var(--color-text-secondary)]">On High Match</label>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={sectionClass}>
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4 flex items-center gap-2">
            <Gauge className="w-5 h-5 text-[var(--color-primary)]" />
            Rate Limit Settings
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Token Bucket Capacity</label>
              <input type="number" min="1" value={form.rate_limit_capacity} onChange={(e) => setForm({ ...form, rate_limit_capacity: Number(e.target.value) })} className={inputClass} />
              <p className="text-[10px] text-[var(--color-text-muted)] mt-1">Max requests per second burst</p>
            </div>
            <div>
              <label className={labelClass}>Refill Rate (tokens/sec)</label>
              <input type="number" min="0.1" step="0.1" value={form.rate_limit_refill_rate} onChange={(e) => setForm({ ...form, rate_limit_refill_rate: Number(e.target.value) })} className={inputClass} />
              <p className="text-[10px] text-[var(--color-text-muted)] mt-1">Tokens added per second</p>
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-6 py-2.5 bg-[#38bdf8] text-[#0f172a] rounded-lg font-medium text-sm hover:bg-[#7dd3fc] disabled:opacity-50 transition-colors"
          >
            {saving ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[#0f172a]" />
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
