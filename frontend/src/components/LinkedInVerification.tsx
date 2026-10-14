import { useEffect, useRef, useState } from 'react';
import { verificationRequest, downloadExport, restoreLinkedInSession } from '../lib/api';

export default function LinkedInVerification() {
  const [phase, setPhase] = useState('closed');
  const [image, setImage] = useState('');
  const [text, setText] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    if (!['starting', 'ready'].includes(phase)) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const state = await verificationRequest<{ phase: string; error?: string }>('status');
        if (stopped) return;
        setPhase(state.phase);
        if (state.error) setMessage(state.error);
        if (state.phase === 'ready') {
          const frame = await verificationRequest<{ image: string }>('frame');
          if (!stopped) setImage(`data:image/jpeg;base64,${frame.image}`);
        }
      } catch (error) { if (!stopped) setMessage(String(error)); }
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [phase]);
  async function input(body: object) {
    try { await verificationRequest('input', body); } catch (error) { setMessage(String(error)); }
  }
  async function action(name: 'start' | 'stop' | 'finish') {
    const previousPhase = phase;
    if (name === 'finish') setPhase('saving');
    if (name === 'stop') setPhase('closing');
    setBusy(true); setMessage('');
    try {
      const result = await verificationRequest<{ phase: string }>(name, {});
      if (alive.current) {
        setPhase(result.phase);
        if (result.phase === 'verified') setMessage('LinkedIn session saved. Download an encrypted backup, then start a dry run in Agent Control.');
        if (result.phase !== 'ready') setImage('');
      }
    } catch (error) { setPhase(previousPhase); setMessage(String(error)); }
    finally { if (alive.current) setBusy(false); }
  }
  const active = ['starting', 'ready'].includes(phase);
  return <section className="rounded-xl border p-5 space-y-3" style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}>
    <h2 className="font-semibold">Verify LinkedIn from your phone</h2>
    <p className="text-sm">Save your LinkedIn email below first. Open the browser, tap its fields, and sign in yourself. Complete any verification manually. This does not submit job applications.</p>
    <p className="text-sm">One browser can run at a time. Close verification before starting an agent. The browser closes after 10 minutes.</p>
    <button className="rounded border px-3 py-2" disabled={busy || active} onClick={() => void action('start')}>Verify LinkedIn</button>
    {active && <button className="rounded border px-3 py-2 ml-2" disabled={busy} onClick={() => void action('stop')}>Close browser</button>}
    {phase === 'starting' && <p>Opening browser…</p>}
    {phase === 'saving' && <p>Checking LinkedIn login and saving the verified session…</p>}
    {phase === 'ready' && <>
      {image && <img src={image} alt="Interactive LinkedIn browser — tap to focus a field or select verification images" className="w-full max-w-[480px] border rounded" draggable={false} onClick={event => {
        const rect = event.currentTarget.getBoundingClientRect();
        void input({ action: 'click', x: Math.min(479, Math.max(0, Math.floor((event.clientX - rect.left) * 480 / rect.width))), y: Math.min(799, Math.max(0, Math.floor((event.clientY - rect.top) * 800 / rect.height))) });
      }} />}
      <label className="block text-sm">Tap a field in the browser above, then enter text here
        <input type="password" autoComplete="off" maxLength={500} value={text} onChange={event => setText(event.target.value)} className="block w-full rounded border p-2 mt-1 bg-transparent" placeholder="Email, password, or verification code" />
      </label>
      <button className="rounded border px-3 py-2" onClick={() => { void input({ action: 'text', text }); setText(''); }}>Type into focused field</button>
      <button className="rounded border px-3 py-2 ml-2" onClick={() => void input({ action: 'clear' })}>Clear focused field</button>
      <div className="flex flex-wrap gap-2">{(['Tab', 'Backspace', 'Enter'] as const).map(key => <button key={key} className="rounded border px-3 py-2" onClick={() => void input({ action: 'key', key })}>{key}</button>)}
        <button className="rounded border px-3 py-2" onClick={() => void input({ action: 'scroll', delta: -500 })}>Scroll up</button>
        <button className="rounded border px-3 py-2" onClick={() => void input({ action: 'scroll', delta: 500 })}>Scroll down</button>
        <button className="rounded border px-3 py-2" onClick={() => void input({ action: 'reload' })}>Reload login</button>
      </div>
      <button className="rounded border px-3 py-2" disabled={busy} onClick={() => void action('finish')}>Save verified session</button>
    </>}
    {message && <p role="status" className="text-sm whitespace-pre-wrap">{message}</p>}
    <p className="text-sm">Free hosting can lose saved data on restart. Keep an encrypted session backup on your phone. You may need to register again, save your LinkedIn email, and upload your resume after a reset. Restore works only while the server encryption key stays the same. LinkedIn may request verification again.</p>
    <button className="rounded border px-3 py-2" onClick={() => void downloadExport('/linkedin/verification/backup', 'linkedin-session.enc').catch(error => setMessage(String(error)))}>Download encrypted session</button>
    <label className="block text-sm">Restore encrypted session
      <input type="file" accept=".enc" disabled={active} onChange={event => {
        const file = event.target.files?.[0];
        if (file) void restoreLinkedInSession(file).then(result => setMessage(result.message)).catch(error => setMessage(String(error)));
        event.target.value = '';
      }} />
    </label>
  </section>;
}
