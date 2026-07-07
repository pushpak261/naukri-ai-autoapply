import { useState, useEffect, useRef, useCallback } from 'react';
import {
  User, Mail, Phone, Briefcase, GraduationCap, Award, Globe, Star,
  Upload, Save, Edit3, X, Plus, Loader2, Check, AlertCircle, GitCompare, History, Download
} from 'lucide-react';
import { api } from '../lib/api';

interface EducationEntry {
  degree: string;
  institution: string;
  year: string;
}

interface WorkExperienceEntry {
  title: string;
  company: string;
  duration: string;
  highlights: string[];
}

interface ResumeProfileData {
  name: string;
  email: string;
  phone: string;
  current_title: string;
  summary: string;
  total_experience_years: number;
  skills: string[];
  technical_skills: string[];
  soft_skills: string[];
  job_titles_held: string[];
  education: EducationEntry[];
  work_experience: WorkExperienceEntry[];
  certifications: string[];
  languages: string[];
  key_achievements: string[];
}

const emptyProfile = (): ResumeProfileData => ({
  name: '', email: '', phone: '', current_title: '', summary: '',
  total_experience_years: 0, skills: [], technical_skills: [], soft_skills: [],
  job_titles_held: [], education: [], work_experience: [], certifications: [],
  languages: [], key_achievements: [],
});

function TagEditor({ tags, onChange, placeholder }: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim();
    if (v && !tags.includes(v)) {
      onChange([...tags, v]);
    }
    setInput('');
  };

  return (
    <div className="flex flex-wrap gap-1.5 mb-2">
      {tags.map((t, i) => (
        <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-[#38bdf8]/10 text-[#38bdf8] rounded-full">
          {t}
          <button onClick={() => onChange(tags.filter((_, j) => j !== i))} className="hover:text-red-400">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <div className="flex gap-1">
        <input
          className="w-28 px-2 py-1 text-xs bg-[#0f172a] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]"
          placeholder={placeholder}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
        />
        <button onClick={add} className="p-1 bg-[#38bdf8]/20 text-[#38bdf8] rounded hover:bg-[#38bdf8]/30">
          <Plus className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

function DropZone({ onFile }: { onFile: (f: File) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  }, [onFile]);

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
        dragging ? 'border-[#38bdf8] bg-[#38bdf8]/5' : 'border-[#334155] hover:border-[#38bdf8]/50'
      }`}
    >
      <Upload className="w-12 h-12 text-[#64748b] mx-auto mb-4" />
      <p className="text-[#94a3b8] font-medium">Drop your resume here or click to browse</p>
      <p className="text-sm text-[#64748b] mt-2">Supports PDF and DOCX</p>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }}
      />
    </div>
  );
}

function SectionCard({ title, icon, children, onEdit, editing }: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  onEdit?: () => void;
  editing?: boolean;
}) {
  return (
    <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          {icon}
          {title}
        </h3>
        {onEdit && (
          <button onClick={onEdit} className={`p-1.5 rounded transition-colors ${
            editing ? 'bg-[#38bdf8]/20 text-[#38bdf8]' : 'text-[#64748b] hover:text-[#94a3b8] hover:bg-[#334155]'
          }`}>
            <Edit3 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function CompactUploadButton({ onUpload, uploading }: { onUpload: (f: File) => void; uploading: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <label className="px-3 py-1.5 text-sm bg-[#38bdf8]/10 text-[#38bdf8] rounded-lg hover:bg-[#38bdf8]/20 transition-colors cursor-pointer flex items-center gap-1.5">
      {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
      Upload
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        disabled={uploading}
        onChange={e => {
          const f = e.target.files?.[0];
          if (f) {
            onUpload(f);
            if (inputRef.current) inputRef.current.value = '';
          }
        }}
      />
    </label>
  );
}

interface VersionEntry {
  id: number;
  label: string;
  timestamp: string;
  profile: ResumeProfileData;
}

const STORAGE_KEY = 'resume_versions';

function loadVersions(): VersionEntry[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch { return []; }
}

function saveVersions(v: VersionEntry[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(v));
}

function computeDiff(a: ResumeProfileData, b: ResumeProfileData): { field: string; before: string; after: string }[] {
  const diff: { field: string; before: string; after: string }[] = [];
  const compareFields: (keyof ResumeProfileData)[] = [
    'name', 'email', 'phone', 'current_title', 'summary', 'total_experience_years',
  ];
  for (const field of compareFields) {
    const va = JSON.stringify(a[field]);
    const vb = JSON.stringify(b[field]);
    if (va !== vb) {
      diff.push({ field, before: String(a[field] ?? ''), after: String(b[field] ?? '') });
    }
  }
  const listFields: (keyof ResumeProfileData)[] = ['skills', 'technical_skills', 'soft_skills', 'certifications', 'languages', 'key_achievements'];
  for (const field of listFields) {
    const va = (a[field] as string[]) || [];
    const vb = (b[field] as string[]) || [];
    if (JSON.stringify(va) !== JSON.stringify(vb)) {
      const removed = va.filter(x => !vb.includes(x));
      const added = vb.filter(x => !va.includes(x));
      const parts: string[] = [];
      if (removed.length) parts.push(`-${removed.join(', ')}`);
      if (added.length) parts.push(`+${added.join(', ')}`);
      diff.push({ field, before: va.join(', '), after: vb.join(', ') });
    }
  }
  return diff;
}

export default function Resume() {
  const [data, setData] = useState<{ exists: boolean; profile: Record<string, unknown> | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<ResumeProfileData>(emptyProfile());
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [editMode, setEditMode] = useState(false);
  const [versions, setVersions] = useState<VersionEntry[]>(loadVersions());
  const [showVersions, setShowVersions] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<VersionEntry | null>(null);
  const [diff, setDiff] = useState<{ field: string; before: string; after: string }[] | null>(null);
  const [snapshotLabel, setSnapshotLabel] = useState('');

  useEffect(() => {
    api.resumeProfile().then(res => {
      setData(res);
      if (res.exists && res.profile) {
        setProfile(res.profile as unknown as ResumeProfileData);
      }
    }).finally(() => setLoading(false));
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.resume.upload(file);
      setProfile(res.profile as unknown as ResumeProfileData);
      setData({ exists: true, profile: res.profile });
      setSuccessMsg('Resume parsed successfully!');
      setEditMode(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccessMsg('');
    try {
      await api.resume.saveProfile(profile as unknown as Record<string, unknown>);
      setData({ exists: true, profile: profile as unknown as Record<string, unknown> });
      const newVersion: VersionEntry = {
        id: Date.now(),
        label: `v${versions.length + 1}`,
        timestamp: new Date().toISOString(),
        profile: { ...profile },
      };
      const updated = [...versions, newVersion];
      saveVersions(updated);
      setVersions(updated);
      setSuccessMsg('Profile saved! Version snapshot created.');
      setEditMode(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const takeSnapshot = () => {
    if (!snapshotLabel.trim()) return;
    const newVersion: VersionEntry = {
      id: Date.now(),
      label: snapshotLabel.trim(),
      timestamp: new Date().toISOString(),
      profile: { ...profile },
    };
    const updated = [...versions, newVersion];
    saveVersions(updated);
    setVersions(updated);
    setSnapshotLabel('');
    setSuccessMsg(`Snapshot "${newVersion.label}" created`);
  };

  const compareVersions = (a: VersionEntry, b: VersionEntry) => {
    setDiff(computeDiff(a.profile, b.profile));
  };

  const update = <K extends keyof ResumeProfileData>(key: K, val: ResumeProfileData[K]) => {
    setProfile(prev => ({ ...prev, [key]: val }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#38bdf8]" />
      </div>
    );
  }

  if (!data?.exists || !data.profile) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-white">Resume Profile</h1>
        {uploading && (
          <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-12 text-center">
            <Loader2 className="w-10 h-10 text-[#38bdf8] mx-auto mb-4 animate-spin" />
            <p className="text-[#94a3b8]">Parsing resume... This may take a moment.</p>
          </div>
        )}
        {!uploading && <DropZone onFile={handleUpload} />}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}
      </div>
    );
  }

  const p = profile;
  const skills = p.skills || [];
  const techSkills = p.technical_skills || [];
  const softSkills = p.soft_skills || [];
  const education = p.education || [];
  const workExperience = p.work_experience || [];
  const certifications = p.certifications || [];
  const languages = p.languages || [];
  const achievements = p.key_achievements || [];

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Resume Profile</h1>
          <p className="text-[#94a3b8] mt-1">Parsed resume information</p>
        </div>
        <div className="flex gap-2">
          {editMode ? (
            <>
              <button
                onClick={() => { setEditMode(false); setProfile(data.profile as unknown as ResumeProfileData); setError(''); }}
                className="px-3 py-1.5 text-sm border border-[#334155] text-[#94a3b8] rounded-lg hover:bg-[#334155] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-3 py-1.5 text-sm bg-[#38bdf8] text-black font-medium rounded-lg hover:bg-[#7dd3fc] transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditMode(true)}
                className="px-3 py-1.5 text-sm border border-[#334155] text-[#94a3b8] rounded-lg hover:bg-[#334155] transition-colors flex items-center gap-1.5"
              >
                <Edit3 className="w-4 h-4" />
                Edit
              </button>
              <CompactUploadButton uploading={uploading} onUpload={(f) => {
                setEditMode(false);
                handleUpload(f);
              }} />
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}
      {successMsg && (
        <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-green-400 text-sm">
          <Check className="w-4 h-4 flex-shrink-0" />
          {successMsg}
        </div>
      )}

      {uploading && (
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-12 text-center">
          <Loader2 className="w-10 h-10 text-[#38bdf8] mx-auto mb-4 animate-spin" />
          <p className="text-[#94a3b8]">Parsing resume... This may take a moment.</p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowVersions(!showVersions)}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors flex items-center gap-1.5 ${
            showVersions ? 'bg-[#38bdf8]/10 text-[#38bdf8] border border-[#38bdf8]/30' : 'border border-[#334155] text-[#94a3b8] hover:bg-[#334155]'
          }`}
        >
          <History className="w-4 h-4" />
          Versions ({versions.length})
        </button>
        {!editMode && (
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={snapshotLabel}
              onChange={e => setSnapshotLabel(e.target.value)}
              placeholder="Label..."
              className="w-28 px-2 py-1.5 text-xs bg-[#0f172a] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]"
            />
            <button
              onClick={takeSnapshot}
              disabled={!snapshotLabel.trim()}
              className="px-2 py-1.5 text-xs bg-[#38bdf8]/10 text-[#38bdf8] rounded-lg hover:bg-[#38bdf8]/20 disabled:opacity-50"
            >
              Snapshot
            </button>
          </div>
        )}
      </div>

      {showVersions && versions.length > 0 && (
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
              <GitCompare className="w-4 h-4 text-[#38bdf8]" />
              Version History
            </h3>
          </div>
          <div className="space-y-2">
            {versions.map((v) => (
              <div key={v.id} className="flex items-center justify-between p-2 rounded-lg hover:bg-[#334155]/50">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-[#38bdf8]">{v.label}</span>
                  <span className="text-xs text-[#64748b]">{new Date(v.timestamp).toLocaleString()}</span>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => setSelectedVersion(selectedVersion?.id === v.id ? null : v)}
                    className={`px-2 py-1 text-xs rounded ${selectedVersion?.id === v.id ? 'bg-[#38bdf8]/20 text-[#38bdf8]' : 'text-[#94a3b8] hover:bg-[#334155]'}`}
                  >
                    {selectedVersion?.id === v.id ? 'Deselect' : 'Compare'}
                  </button>
                  {selectedVersion && selectedVersion.id !== v.id && (
                    <button
                      onClick={() => compareVersions(selectedVersion, v)}
                      className="px-2 py-1 text-xs bg-yellow-500/10 text-yellow-400 rounded hover:bg-yellow-500/20"
                    >
                      Diff
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {diff && diff.length > 0 && (
            <div className="mt-4 border-t border-[#334155] pt-3">
              <h4 className="text-xs font-semibold text-white mb-2">Changes ({diff.length})</h4>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {diff.map((d, i) => (
                  <div key={i} className="p-2 bg-[#0f172a] rounded-lg">
                    <p className="text-[10px] uppercase text-[#64748b] mb-1">{d.field}</p>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="p-1.5 bg-red-500/5 border border-red-500/20 rounded text-xs text-red-300">
                        <span className="text-[10px] text-red-500 block mb-0.5">Before</span>
                        {d.before || <span className="italic text-[#64748b]">empty</span>}
                      </div>
                      <div className="p-1.5 bg-green-500/5 border border-green-500/20 rounded text-xs text-green-300">
                        <span className="text-[10px] text-green-500 block mb-0.5">After</span>
                        {d.after || <span className="italic text-[#64748b]">empty</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {diff && diff.length === 0 && (
            <p className="text-xs text-[#64748b] mt-2">No differences between selected versions.</p>
          )}
        </div>
      )}

      {!uploading && (<div className="bg-[#1e293b] rounded-xl border border-[#334155] p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-[#38bdf8]/10 rounded-xl">
            <User className="w-8 h-8 text-[#38bdf8]" />
          </div>
          <div className="flex-1">
            {editMode ? (
              <div className="space-y-3">
                <input className="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={p.name} onChange={e => update('name', e.target.value)} placeholder="Full name" />
                <input className="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={p.current_title} onChange={e => update('current_title', e.target.value)} placeholder="Current title" />
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="flex items-center gap-2 bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2">
                    <Mail className="w-4 h-4 text-[#64748b]" />
                    <input className="flex-1 bg-transparent text-white text-sm placeholder-[#64748b] outline-none" value={p.email} onChange={e => update('email', e.target.value)} placeholder="Email" />
                  </div>
                  <div className="flex items-center gap-2 bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2">
                    <Phone className="w-4 h-4 text-[#64748b]" />
                    <input className="flex-1 bg-transparent text-white text-sm placeholder-[#64748b] outline-none" value={p.phone} onChange={e => update('phone', e.target.value)} placeholder="Phone" />
                  </div>
                  <div className="flex items-center gap-2 bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2">
                    <Briefcase className="w-4 h-4 text-[#64748b]" />
                    <input className="flex-1 bg-transparent text-white text-sm placeholder-[#64748b] outline-none" type="number" step="0.1" value={p.total_experience_years} onChange={e => update('total_experience_years', parseFloat(e.target.value) || 0)} placeholder="Years exp" />
                    <span className="text-xs text-[#64748b]">years</span>
                  </div>
                </div>
              </div>
            ) : (
              <>
                <h2 className="text-xl font-bold text-white">{p.name || 'Unknown'}</h2>
                {p.current_title && <p className="text-[#94a3b8] mt-1">{p.current_title}</p>}
                <div className="flex flex-wrap gap-4 mt-3 text-sm">
                  {p.email && (
                    <span className="flex items-center gap-1.5 text-[#94a3b8]"><Mail className="w-4 h-4" />{p.email}</span>
                  )}
                  {p.phone && (
                    <span className="flex items-center gap-1.5 text-[#94a3b8]"><Phone className="w-4 h-4" />{p.phone}</span>
                  )}
                  {p.total_experience_years > 0 && (
                    <span className="flex items-center gap-1.5 text-[#94a3b8]"><Briefcase className="w-4 h-4" />{p.total_experience_years} years experience</span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {editMode ? (
          <div className="mt-4">
            <textarea
              className="w-full px-3 py-2 bg-[#0f172a] border border-[#334155] rounded-lg text-white text-sm placeholder-[#64748b] outline-none focus:border-[#38bdf8] resize-none"
              rows={3}
              value={p.summary}
              onChange={e => update('summary', e.target.value)}
              placeholder="Professional summary"
            />
          </div>
        ) : p.summary && (
          <div className="mt-4 p-3 bg-[#0f172a] rounded-lg">
            <p className="text-sm text-[#94a3b8] leading-relaxed">{p.summary}</p>
          </div>
        )}
      </div>)}

      {editMode ? (
        <>
          <SectionCard title={`All Skills (${skills.length})`} icon={<Star className="w-4 h-4 text-[#38bdf8]" />}>
            <TagEditor tags={skills} onChange={v => update('skills', v)} placeholder="Add skill" />
          </SectionCard>

          <SectionCard title={`Technical Skills (${techSkills.length})`} icon={<Award className="w-4 h-4 text-green-400" />}>
            <TagEditor tags={techSkills} onChange={v => update('technical_skills', v)} placeholder="Add tech skill" />
          </SectionCard>

          <SectionCard title={`Soft Skills (${softSkills.length})`} icon={<Star className="w-4 h-4 text-purple-400" />}>
            <TagEditor tags={softSkills} onChange={v => update('soft_skills', v)} placeholder="Add soft skill" />
          </SectionCard>

          <SectionCard title={`Work Experience (${workExperience.length})`} icon={<Briefcase className="w-4 h-4 text-[#38bdf8]" />}>
            {workExperience.map((exp, i) => (
              <div key={i} className="p-3 bg-[#0f172a] rounded-lg mb-2 space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  <input className="col-span-2 px-2 py-1 text-sm bg-[#1e293b] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={exp.title} onChange={e => {
                    const next = [...workExperience];
                    next[i] = { ...next[i], title: e.target.value };
                    update('work_experience', next);
                  }} placeholder="Title" />
                  <input className="px-2 py-1 text-sm bg-[#1e293b] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={exp.company} onChange={e => {
                    const next = [...workExperience];
                    next[i] = { ...next[i], company: e.target.value };
                    update('work_experience', next);
                  }} placeholder="Company" />
                </div>
                <input className="w-full px-2 py-1 text-sm bg-[#1e293b] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={exp.duration} onChange={e => {
                  const next = [...workExperience];
                  next[i] = { ...next[i], duration: e.target.value };
                  update('work_experience', next);
                }} placeholder="Duration (e.g. Jan 2020 - Present)" />
                <TagEditor tags={exp.highlights} onChange={v => {
                  const next = [...workExperience];
                  next[i] = { ...next[i], highlights: v };
                  update('work_experience', next);
                }} placeholder="Add highlight" />
              </div>
            ))}
            <button onClick={() => update('work_experience', [...workExperience, { title: '', company: '', duration: '', highlights: [] }])} className="text-xs text-[#38bdf8] hover:text-[#7dd3fc] flex items-center gap-1">
              <Plus className="w-3 h-3" /> Add experience
            </button>
          </SectionCard>

          <SectionCard title={`Education (${education.length})`} icon={<GraduationCap className="w-4 h-4 text-[#38bdf8]" />}>
            {education.map((edu, i) => (
              <div key={i} className="p-3 bg-[#0f172a] rounded-lg mb-2 grid grid-cols-3 gap-2">
                <input className="px-2 py-1 text-sm bg-[#1e293b] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={edu.degree} onChange={e => {
                  const next = [...education];
                  next[i] = { ...next[i], degree: e.target.value };
                  update('education', next);
                }} placeholder="Degree" />
                <input className="px-2 py-1 text-sm bg-[#1e293b] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={edu.institution} onChange={e => {
                  const next = [...education];
                  next[i] = { ...next[i], institution: e.target.value };
                  update('education', next);
                }} placeholder="Institution" />
                <input className="px-2 py-1 text-sm bg-[#1e293b] border border-[#334155] rounded text-white placeholder-[#64748b] outline-none focus:border-[#38bdf8]" value={edu.year} onChange={e => {
                  const next = [...education];
                  next[i] = { ...next[i], year: e.target.value };
                  update('education', next);
                }} placeholder="Year" />
              </div>
            ))}
            <button onClick={() => update('education', [...education, { degree: '', institution: '', year: '' }])} className="text-xs text-[#38bdf8] hover:text-[#7dd3fc] flex items-center gap-1">
              <Plus className="w-3 h-3" /> Add education
            </button>
          </SectionCard>

          <SectionCard title={`Certifications (${certifications.length})`} icon={<Award className="w-4 h-4 text-yellow-400" />}>
            <TagEditor tags={certifications} onChange={v => update('certifications', v)} placeholder="Add certification" />
          </SectionCard>

          <SectionCard title={`Languages (${languages.length})`} icon={<Globe className="w-4 h-4 text-[#38bdf8]" />}>
            <TagEditor tags={languages} onChange={v => update('languages', v)} placeholder="Add language" />
          </SectionCard>

          <SectionCard title={`Key Achievements (${achievements.length})`} icon={<Star className="w-4 h-4 text-yellow-400" />}>
            <TagEditor tags={achievements} onChange={v => update('key_achievements', v)} placeholder="Add achievement" />
          </SectionCard>
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {skills.length > 0 && (
              <SectionCard title={`All Skills (${skills.length})`} icon={<Star className="w-4 h-4 text-[#38bdf8]" />}>
                <div className="flex flex-wrap gap-1.5">
                  {skills.map(s => (
                    <span key={s} className="px-2.5 py-1 text-xs bg-[#38bdf8]/10 text-[#38bdf8] rounded-full">{s}</span>
                  ))}
                </div>
              </SectionCard>
            )}
            {techSkills.length > 0 && (
              <SectionCard title={`Technical Skills (${techSkills.length})`} icon={<Award className="w-4 h-4 text-green-400" />}>
                <div className="flex flex-wrap gap-1.5">
                  {techSkills.map(s => (
                    <span key={s} className="px-2.5 py-1 text-xs bg-green-500/10 text-green-400 rounded-full">{s}</span>
                  ))}
                </div>
              </SectionCard>
            )}
            {softSkills.length > 0 && (
              <SectionCard title={`Soft Skills (${softSkills.length})`} icon={<Star className="w-4 h-4 text-purple-400" />}>
                <div className="flex flex-wrap gap-1.5">
                  {softSkills.map(s => (
                    <span key={s} className="px-2.5 py-1 text-xs bg-purple-500/10 text-purple-400 rounded-full">{s}</span>
                  ))}
                </div>
              </SectionCard>
            )}
          </div>

          {workExperience.length > 0 && (
            <SectionCard title="Work Experience" icon={<Briefcase className="w-4 h-4 text-[#38bdf8]" />}>
              <div className="space-y-4">
                {workExperience.map((exp, i) => (
                  <div key={i} className="p-3 bg-[#0f172a] rounded-lg">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm font-medium text-white">{exp.title}</p>
                        <p className="text-xs text-[#94a3b8]">{exp.company}</p>
                      </div>
                      {exp.duration && <span className="text-xs text-[#64748b]">{exp.duration}</span>}
                    </div>
                    {exp.highlights && exp.highlights.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {exp.highlights.map((h, j) => (
                          <li key={j} className="text-xs text-[#94a3b8] flex items-start gap-1.5">
                            <span className="text-[#38bdf8] mt-0.5">•</span>
                            {h}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {education.length > 0 && (
            <SectionCard title="Education" icon={<GraduationCap className="w-4 h-4 text-[#38bdf8]" />}>
              <div className="space-y-3">
                {education.map((edu, i) => (
                  <div key={i} className="flex items-start justify-between p-3 bg-[#0f172a] rounded-lg">
                    <div>
                      <p className="text-sm font-medium text-white">{edu.degree}</p>
                      <p className="text-xs text-[#94a3b8]">{edu.institution}</p>
                    </div>
                    {edu.year && <span className="text-xs text-[#64748b]">{edu.year}</span>}
                  </div>
                ))}
              </div>
            </SectionCard>
          )}

          {certifications.length > 0 && (
            <SectionCard title={`Certifications (${certifications.length})`} icon={<Award className="w-4 h-4 text-yellow-400" />}>
              <div className="flex flex-wrap gap-1.5">
                {certifications.map(c => (
                  <span key={c} className="px-2.5 py-1 text-xs bg-yellow-500/10 text-yellow-400 rounded-full">{c}</span>
                ))}
              </div>
            </SectionCard>
          )}

          {languages.length > 0 && (
            <SectionCard title={`Languages (${languages.length})`} icon={<Globe className="w-4 h-4 text-[#38bdf8]" />}>
              <div className="flex flex-wrap gap-1.5">
                {languages.map(l => (
                  <span key={l} className="px-2.5 py-1 text-xs bg-[#38bdf8]/10 text-[#38bdf8] rounded-full">{l}</span>
                ))}
              </div>
            </SectionCard>
          )}

          {achievements.length > 0 && (
            <SectionCard title={`Key Achievements (${achievements.length})`} icon={<Star className="w-4 h-4 text-yellow-400" />}>
              <ul className="space-y-1.5">
                {achievements.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#94a3b8]">
                    <span className="text-yellow-400 mt-0.5">★</span>
                    {a}
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}
        </>
      )}
    </div>
  );
}
