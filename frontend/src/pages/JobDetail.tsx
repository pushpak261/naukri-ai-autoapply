import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Building2, MapPin, DollarSign, Clock, Award, AlertCircle } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import CareerStudio from '../components/CareerStudio';
import { api } from '../lib/api';

export default function JobDetail() {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState('');
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id);
  const validId = Number.isSafeInteger(jobId) && jobId > 0;
  const result = useQuery({
    queryKey: ['job', jobId], queryFn: () => api.job(jobId), enabled: validId,
  });
  const job = result.data;
  const loading = validId && result.isPending;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--color-primary)]" />
      </div>
    );
  }

  if (result.isError) return <div role="alert" className="notice-error"><p>{result.error.message}</p><button className="secondary-button" onClick={() => result.refetch()}>Retry job details</button><Link to="/jobs">Back to jobs</Link></div>;
  if (!job) return <div role="alert" className="text-red-400">Job not found. <Link to="/jobs">Back to jobs</Link></div>;

  return (
    <div className="space-y-6 max-w-4xl">
      <Link to="/jobs" className="inline-flex items-center gap-1.5 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Jobs
      </Link>

      <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-[var(--color-text)] break-words">{job.title}</h1>
            <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-[var(--color-text-secondary)]">
              <span className="flex items-center gap-1">
                <Building2 className="w-4 h-4" />
                {job.company}
              </span>
              {job.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="w-4 h-4" />
                  {job.location}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 mt-2 text-xs text-[var(--color-text-muted)]">
              {job.experience && <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />{job.experience}</span>}
              {job.salary && <span className="flex items-center gap-1"><DollarSign className="w-3.5 h-3.5" />{job.salary}</span>}
              {job.posted_date && <span>Posted: {job.posted_date}</span>}
            </div>
          </div>
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1.5 px-4 py-2 bg-[#38bdf8]/10 text-[var(--color-primary)] rounded-lg text-sm font-medium hover:bg-[#38bdf8]/20 transition-colors w-full sm:w-auto"
            >
            <ExternalLink className="w-4 h-4" />
            View original listing
          </a>
        </div>

        {job.skills && (
          <div className="flex flex-wrap gap-1.5 mt-4">
            {job.skills.split(',').map((skill) => (
              <span key={skill} className="px-2.5 py-1 text-xs bg-[#38bdf8]/10 text-[var(--color-primary)] rounded-full">
                {skill.trim()}
              </span>
            ))}
          </div>
        )}
        <button className="primary-button mt-4" disabled={starting || ['applied', 'applying', 'uncertain', 'skipped_already_applied'].includes(job.application?.status ?? '')}
          onClick={async () => {
            setStarting(true);
            setStartError('');
            try {
              const result = await api.agent.start(job.source === 'linkedin' ? 'linkedin' : 'naukri', 0, [job.id]);
              if (result.status !== 'started') throw new Error(result.message || 'An agent is already running. Stop it before starting this listing.');
              navigate('/agent-control');
            } catch (err) { setStartError(err instanceof Error ? err.message : 'Could not start this application'); }
            finally { setStarting(false); }
          }}>{starting ? 'Starting…' : 'Run agent for this job'}</button>
        {startError && <p role="alert" className="text-red-400 mt-2">{startError}</p>}
      </div>

      <CareerStudio jobId={jobId} key={jobId} />
      {job.application && (
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-6">
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4">Application Details</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Status</p>
              <StatusBadge status={job.application.status} className="mt-1" />
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Match Score</p>
              <p className={`text-lg font-bold mt-1 ${
                job.application.match_score >= 80 ? 'text-green-400' : job.application.match_score >= 50 ? 'text-yellow-400' : 'text-red-400'
              }`}>
                {job.application.match_score.toFixed(0)}%
              </p>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">Applied At</p>
              <p className="text-sm text-[var(--color-text)] mt-1">{job.application.applied_at.slice(0, 16).replace('T', ' ')}</p>
            </div>
          </div>

          {job.application.match_reasoning && (
            <div className="mt-3">
              <p className="text-xs text-[var(--color-text-muted)] mb-1">Reasoning</p>
              <p className="text-sm text-[var(--color-text-secondary)] bg-[var(--color-bg)] rounded-lg p-3">{job.application.match_reasoning}</p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            {job.application.matching_skills && (
              <div>
                <p className="text-xs text-[var(--color-text-muted)] mb-1 flex items-center gap-1">
                  <Award className="w-3.5 h-3.5 text-green-400" />
                  Matching Skills
                </p>
                <div className="flex flex-wrap gap-1">
                  {job.application.matching_skills.split(',').map((s) => (
                    <span key={s} className="px-2 py-0.5 text-xs bg-green-500/10 text-green-400 rounded-full">
                      {s.trim()}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {job.application.missing_skills && (
              <div>
                <p className="text-xs text-[var(--color-text-muted)] mb-1 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5 text-yellow-400" />
                  Missing Skills
                </p>
                <div className="flex flex-wrap gap-1">
                  {job.application.missing_skills.split(',').map((s) => (
                    <span key={s} className="px-2 py-0.5 text-xs bg-yellow-500/10 text-yellow-400 rounded-full">
                      {s.trim()}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {job.application.error_message && (
            <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
              <p className="text-xs text-red-400 font-medium">Error</p>
              <p className="text-sm text-red-300 mt-1">{job.application.error_message}</p>
            </div>
          )}
        </div>
      )}

      {job.description && (
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-6">
          <h2 className="text-lg font-semibold text-[var(--color-text)] mb-4">Job Description</h2>
          <div className="text-sm text-[var(--color-text-secondary)] leading-relaxed whitespace-pre-wrap">
            {job.description}
          </div>
        </div>
      )}
    </div>
  );
}
