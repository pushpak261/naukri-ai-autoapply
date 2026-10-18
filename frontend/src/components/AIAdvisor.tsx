import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Sparkles } from 'lucide-react';
import { api, type AIAdvice } from '../lib/api';

const pages: Record<string, { feature: string; title: string }> = {
  '/': { feature: 'overview', title: 'Plan my next steps' },
  '/jobs': { feature: 'jobs', title: 'Review my job matches' },
  '/applications': { feature: 'applications', title: 'Review my application strategy' },
  '/copilot': { feature: 'copilot', title: 'Build my career action plan' },
  '/skills-gap': { feature: 'skills', title: 'Create my learning plan' },
  '/market-intelligence': { feature: 'market', title: 'Interpret my saved job listings' },
  '/scam-detector': { feature: 'scam', title: 'Review listing risk signals' },
  '/resume': { feature: 'resume', title: 'Review my resume with AI' },
  '/agent-control': { feature: 'agent', title: 'Recommend my agent settings' },
  '/analytics': { feature: 'analytics', title: 'Explain my results' },
  '/job-inspector': { feature: 'jobs', title: 'Review saved listings with AI' },
  '/autopilot': { feature: 'agent', title: 'Recommend my agent settings' },
  '/linkedin': { feature: 'agent', title: 'Recommend my LinkedIn strategy' },
};

export default function AIAdvisor() {
  const { pathname } = useLocation();
  const jobMatch = pathname.match(/^\/jobs\/(\d+)$/);
  const page = jobMatch ? { feature: 'jobs', title: 'Analyze this job with AI' } : pages[pathname];
  const [result, setResult] = useState<AIAdvice | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    pending.current?.abort();
    pending.current = null;
    setResult(null); setError(''); setLoading(false);
    return () => { pending.current?.abort(); pending.current = null; };
  }, [pathname]);
  if (!page) return null;

  const generate = async () => {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 110_000);
    setLoading(true); setError(''); setResult(null);
    try {
      const response = await api.aiAdvice(page.feature, jobMatch ? Number(jobMatch[1]) : undefined, controller.signal);
      if (!controller.signal.aborted) setResult(response);
    } catch (e) {
      if (pending.current === controller) setError(controller.signal.aborted ? 'AI request timed out. Please retry.' : e instanceof Error ? e.message : 'AI request failed. Please retry.');
    } finally {
      window.clearTimeout(timeout);
      if (pending.current === controller) { pending.current = null; setLoading(false); }
    }
  };

  return <section aria-label="Gemini AI advisor" className="mt-6 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-3">
    <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={18} className="text-[var(--color-primary)]" />Gemini AI advisor</h2>
    <p className="text-sm text-[var(--color-text-secondary)]">Get advice using your saved resume and up to 20 recent listings. Relevant profile and listing details are sent to Gemini when you click. Review suggestions before acting.</p>
    <button type="button" className="primary-button" disabled={loading} onClick={generate}>{loading ? 'Analyzing with Gemini…' : page.title}</button>
    {error && <div role="alert" className="text-sm text-red-400">{error} <Link to="/config#ai-settings" className="underline">AI settings</Link></div>}
    {result && <div aria-live="polite" className="space-y-3 text-sm">
      <p>{result.summary}</p>
      <ol className="list-decimal pl-5 space-y-2">{result.recommendations.map((item, index) => <li key={index}>{item}</li>)}</ol>
      {result.cautions.length > 0 && <div><h3 className="font-semibold">Evidence and cautions</h3><ul className="list-disc pl-5 space-y-1">{result.cautions.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
      <p className="text-xs text-[var(--color-text-secondary)]">Generated with {result.model} · {result.jobs_reviewed} listings · {result.applications_reviewed} recent application records. Advice does not change settings or submit applications.</p>
    </div>}
  </section>;
}
