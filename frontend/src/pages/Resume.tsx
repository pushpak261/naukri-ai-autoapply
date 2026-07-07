import { useState, useEffect, useRef, useCallback } from 'react';
import {
  User, Mail, Phone, Briefcase, GraduationCap, Award, Globe, Star,
  Upload, Save, Edit3, X, Plus, Loader2, Check, AlertCircle
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
        <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-primary/10 text-primary rounded-full">
          {t}
          <button onClick={() => onChange(tags.filter((_, j) => j !== i))} className="hover:text-red-400">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <div className="flex gap-1">
        <input
          className="w-28 px-2 py-1 text-xs bg-bg border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary"
          placeholder={placeholder}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
        />
        <button onClick={add} className="p-1 bg-primary/20 text-primary rounded hover:bg-primary/30">
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
        dragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/50'
      }`}
    >
      <Upload className="w-12 h-12 text-muted mx-auto mb-4" />
      <p className="text-secondary font-medium">Drop your resume here or click to browse</p>
      <p className="text-sm text-muted mt-2">Supports PDF and DOCX</p>
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
    <div className="bg-surface rounded-xl border border-border p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text flex items-center gap-2">
          {icon}
          {title}
        </h3>
        {onEdit && (
          <button onClick={onEdit} className={`p-1.5 rounded transition-colors ${
            editing ? 'bg-primary/20 text-primary' : 'text-muted hover:text-secondary hover:bg-surface-hover'
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
    <label className="px-3 py-1.5 text-sm bg-primary/10 text-primary rounded-lg hover:bg-primary/20 transition-colors cursor-pointer flex items-center gap-1.5">
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

export default function Resume() {
  const [data, setData] = useState<{ exists: boolean; profile: Record<string, unknown> | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<ResumeProfileData>(emptyProfile());
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [editMode, setEditMode] = useState(false);

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
      setSuccessMsg('Profile saved!');
      setEditMode(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const update = <K extends keyof ResumeProfileData>(key: K, val: ResumeProfileData[K]) => {
    setProfile(prev => ({ ...prev, [key]: val }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (!data?.exists || !data.profile) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-text">Resume Profile</h1>
        {uploading && (
          <div className="bg-surface rounded-xl border border-border p-12 text-center">
            <Loader2 className="w-10 h-10 text-primary mx-auto mb-4 animate-spin" />
            <p className="text-secondary">Parsing resume... This may take a moment.</p>
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
          <h1 className="text-2xl font-bold text-text">Resume Profile</h1>
          <p className="text-secondary mt-1">Parsed resume information</p>
        </div>
        <div className="flex gap-2">
          {editMode ? (
            <>
              <button
                onClick={() => { setEditMode(false); setProfile(data.profile as unknown as ResumeProfileData); setError(''); }}
                className="px-3 py-1.5 text-sm border border-border text-secondary rounded-lg hover:bg-surface-hover transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-3 py-1.5 text-sm bg-primary text-on-primary font-medium rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditMode(true)}
                className="px-3 py-1.5 text-sm border border-border text-secondary rounded-lg hover:bg-surface-hover transition-colors flex items-center gap-1.5"
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
        <div className="bg-surface rounded-xl border border-border p-12 text-center">
          <Loader2 className="w-10 h-10 text-primary mx-auto mb-4 animate-spin" />
          <p className="text-secondary">Parsing resume... This may take a moment.</p>
        </div>
      )}

      {!uploading && (<div className="bg-surface rounded-xl border border-border p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-primary/10 rounded-xl">
            <User className="w-8 h-8 text-primary" />
          </div>
          <div className="flex-1">
            {editMode ? (
              <div className="space-y-3">
                <input className="w-full px-3 py-2 bg-bg border border-border rounded-lg text-text placeholder:text-muted outline-none focus:border-primary" value={p.name} onChange={e => update('name', e.target.value)} placeholder="Full name" />
                <input className="w-full px-3 py-2 bg-bg border border-border rounded-lg text-text placeholder:text-muted outline-none focus:border-primary" value={p.current_title} onChange={e => update('current_title', e.target.value)} placeholder="Current title" />
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="flex items-center gap-2 bg-bg border border-border rounded-lg px-3 py-2">
                    <Mail className="w-4 h-4 text-muted" />
                    <input className="flex-1 bg-transparent text-text text-sm placeholder:text-muted outline-none" value={p.email} onChange={e => update('email', e.target.value)} placeholder="Email" />
                  </div>
                  <div className="flex items-center gap-2 bg-bg border border-border rounded-lg px-3 py-2">
                    <Phone className="w-4 h-4 text-muted" />
                    <input className="flex-1 bg-transparent text-text text-sm placeholder:text-muted outline-none" value={p.phone} onChange={e => update('phone', e.target.value)} placeholder="Phone" />
                  </div>
                  <div className="flex items-center gap-2 bg-bg border border-border rounded-lg px-3 py-2">
                    <Briefcase className="w-4 h-4 text-muted" />
                    <input className="flex-1 bg-transparent text-text text-sm placeholder:text-muted outline-none" type="number" step="0.1" value={p.total_experience_years} onChange={e => update('total_experience_years', parseFloat(e.target.value) || 0)} placeholder="Years exp" />
                    <span className="text-xs text-muted">years</span>
                  </div>
                </div>
              </div>
            ) : (
              <>
                <h2 className="text-xl font-bold text-text">{p.name || 'Unknown'}</h2>
                {p.current_title && <p className="text-secondary mt-1">{p.current_title}</p>}
                <div className="flex flex-wrap gap-4 mt-3 text-sm">
                  {p.email && (
                    <span className="flex items-center gap-1.5 text-secondary"><Mail className="w-4 h-4" />{p.email}</span>
                  )}
                  {p.phone && (
                    <span className="flex items-center gap-1.5 text-secondary"><Phone className="w-4 h-4" />{p.phone}</span>
                  )}
                  {p.total_experience_years > 0 && (
                    <span className="flex items-center gap-1.5 text-secondary"><Briefcase className="w-4 h-4" />{p.total_experience_years} years experience</span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {editMode ? (
          <div className="mt-4">
            <textarea
              className="w-full px-3 py-2 bg-bg border border-border rounded-lg text-text text-sm placeholder:text-muted outline-none focus:border-primary resize-none"
              rows={3}
              value={p.summary}
              onChange={e => update('summary', e.target.value)}
              placeholder="Professional summary"
            />
          </div>
        ) : p.summary && (
          <div className="mt-4 p-3 bg-bg rounded-lg">
            <p className="text-sm text-secondary leading-relaxed">{p.summary}</p>
          </div>
        )}
      </div>)}

      {editMode ? (
        <>
          <SectionCard title={`All Skills (${skills.length})`} icon={<Star className="w-4 h-4 text-primary" />}>
            <TagEditor tags={skills} onChange={v => update('skills', v)} placeholder="Add skill" />
          </SectionCard>

          <SectionCard title={`Technical Skills (${techSkills.length})`} icon={<Award className="w-4 h-4 text-green-400" />}>
            <TagEditor tags={techSkills} onChange={v => update('technical_skills', v)} placeholder="Add tech skill" />
          </SectionCard>

          <SectionCard title={`Soft Skills (${softSkills.length})`} icon={<Star className="w-4 h-4 text-purple-400" />}>
            <TagEditor tags={softSkills} onChange={v => update('soft_skills', v)} placeholder="Add soft skill" />
          </SectionCard>

          <SectionCard title={`Work Experience (${workExperience.length})`} icon={<Briefcase className="w-4 h-4 text-primary" />}>
            {workExperience.map((exp, i) => (
              <div key={i} className="p-3 bg-bg rounded-lg mb-2 space-y-2">
                <div className="grid grid-cols-3 gap-2">
                  <input className="col-span-2 px-2 py-1 text-sm bg-surface border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary" value={exp.title} onChange={e => {
                    const next = [...workExperience];
                    next[i] = { ...next[i], title: e.target.value };
                    update('work_experience', next);
                  }} placeholder="Title" />
                  <input className="px-2 py-1 text-sm bg-surface border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary" value={exp.company} onChange={e => {
                    const next = [...workExperience];
                    next[i] = { ...next[i], company: e.target.value };
                    update('work_experience', next);
                  }} placeholder="Company" />
                </div>
                <input className="w-full px-2 py-1 text-sm bg-surface border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary" value={exp.duration} onChange={e => {
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
            <button onClick={() => update('work_experience', [...workExperience, { title: '', company: '', duration: '', highlights: [] }])} className="text-xs text-primary hover:text-primary-hover flex items-center gap-1">
              <Plus className="w-3 h-3" /> Add experience
            </button>
          </SectionCard>

          <SectionCard title={`Education (${education.length})`} icon={<GraduationCap className="w-4 h-4 text-primary" />}>
            {education.map((edu, i) => (
              <div key={i} className="p-3 bg-bg rounded-lg mb-2 grid grid-cols-3 gap-2">
                <input className="px-2 py-1 text-sm bg-surface border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary" value={edu.degree} onChange={e => {
                  const next = [...education];
                  next[i] = { ...next[i], degree: e.target.value };
                  update('education', next);
                }} placeholder="Degree" />
                <input className="px-2 py-1 text-sm bg-surface border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary" value={edu.institution} onChange={e => {
                  const next = [...education];
                  next[i] = { ...next[i], institution: e.target.value };
                  update('education', next);
                }} placeholder="Institution" />
                <input className="px-2 py-1 text-sm bg-surface border border-border rounded text-text placeholder:text-muted outline-none focus:border-primary" value={edu.year} onChange={e => {
                  const next = [...education];
                  next[i] = { ...next[i], year: e.target.value };
                  update('education', next);
                }} placeholder="Year" />
              </div>
            ))}
            <button onClick={() => update('education', [...education, { degree: '', institution: '', year: '' }])} className="text-xs text-primary hover:text-primary-hover flex items-center gap-1">
              <Plus className="w-3 h-3" /> Add education
            </button>
          </SectionCard>

          <SectionCard title={`Certifications (${certifications.length})`} icon={<Award className="w-4 h-4 text-yellow-400" />}>
            <TagEditor tags={certifications} onChange={v => update('certifications', v)} placeholder="Add certification" />
          </SectionCard>

          <SectionCard title={`Languages (${languages.length})`} icon={<Globe className="w-4 h-4 text-primary" />}>
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
              <SectionCard title={`All Skills (${skills.length})`} icon={<Star className="w-4 h-4 text-primary" />}>
                <div className="flex flex-wrap gap-1.5">
                  {skills.map(s => (
                    <span key={s} className="px-2.5 py-1 text-xs bg-primary/10 text-primary rounded-full">{s}</span>
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
            <SectionCard title="Work Experience" icon={<Briefcase className="w-4 h-4 text-primary" />}>
              <div className="space-y-4">
                {workExperience.map((exp, i) => (
                  <div key={i} className="p-3 bg-bg rounded-lg">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm font-medium text-text">{exp.title}</p>
                        <p className="text-xs text-secondary">{exp.company}</p>
                      </div>
                      {exp.duration && <span className="text-xs text-muted">{exp.duration}</span>}
                    </div>
                    {exp.highlights && exp.highlights.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {exp.highlights.map((h, j) => (
                          <li key={j} className="text-xs text-secondary flex items-start gap-1.5">
                            <span className="text-primary mt-0.5">•</span>
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
            <SectionCard title="Education" icon={<GraduationCap className="w-4 h-4 text-primary" />}>
              <div className="space-y-3">
                {education.map((edu, i) => (
                  <div key={i} className="flex items-start justify-between p-3 bg-bg rounded-lg">
                    <div>
                      <p className="text-sm font-medium text-text">{edu.degree}</p>
                      <p className="text-xs text-secondary">{edu.institution}</p>
                    </div>
                    {edu.year && <span className="text-xs text-muted">{edu.year}</span>}
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
            <SectionCard title={`Languages (${languages.length})`} icon={<Globe className="w-4 h-4 text-primary" />}>
              <div className="flex flex-wrap gap-1.5">
                {languages.map(l => (
                  <span key={l} className="px-2.5 py-1 text-xs bg-primary/10 text-primary rounded-full">{l}</span>
                ))}
              </div>
            </SectionCard>
          )}

          {achievements.length > 0 && (
            <SectionCard title={`Key Achievements (${achievements.length})`} icon={<Star className="w-4 h-4 text-yellow-400" />}>
              <ul className="space-y-1.5">
                {achievements.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-secondary">
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
