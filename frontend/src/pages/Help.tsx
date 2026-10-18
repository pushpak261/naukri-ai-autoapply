import { Link } from 'react-router-dom';
import { ArrowUpRight,FileText,SlidersHorizontal,ShieldCheck,Play,LifeBuoy } from 'lucide-react';
import { brand } from '../lib/brand';
export default function Help() {
  return <div className="space-y-6">
    <div className="overview-intro">
      <div>
        <p className="eyebrow">GETTING STARTED</p>
        <h1>A thoughtful search starts here.</h1>
        <p className="muted">Set up {brand.name} once, then review and refine as you go.</p>
      </div>
      <LifeBuoy size={38} className="accent" />
    </div>
      <div className="help-steps">{[{ icon: FileText,title: 'Start with your resume',text: 'Open Resume & profile to upload your resume and review the extracted information. Accurate skills and experience help matching assess opportunities.',to: '/resume',link: 'Review your resume' },{ icon: SlidersHorizontal,title: 'Define a focused search',text: 'In Preferences, set job keywords, locations, experience, and your match threshold. Choose a sensible daily application cap and review your profile answers.',to: '/config',link: 'Set preferences' },{ icon: ShieldCheck,title: 'Connect your platform',text: 'Use Connected accounts to configure your account credentials. Open Command center for Naukri session and login controls. LinkedIn has its own workspace and configuration.',to: '/accounts',link: 'Manage accounts' },{ icon: Play,title: 'Preview before you apply',text: 'Enable dry run in Preferences and start a search in Command center. Inspect jobs, matches, and run logs. Switch to live applications only when the settings suit your needs.',to: '/agent-control',link: 'Open command center' }].map((s,i) => <section className="workspace-panel help-step" key={s.title}>
      <span className="help-number">0{i+1}</span>
      <s.icon size={23} className="accent" />
      <h2>{s.title}</h2>
      <p className="muted">{s.text}</p>
      <Link to={s.to} className="text-link">{s.link}<ArrowUpRight size={15} />
      </Link>
    </section>)}</div>
    <section className="workspace-panel">
      <h2 className="mb-4">Common questions</h2>{[{ q: 'Why are there no jobs or charts yet?',a: 'A new account starts with an empty workspace. Jobs and application activity appear after searches run. An empty chart is expected before your first run.' },{ q: 'What happens when a session expires?',a: 'Open Command center and review the Naukri session status, then use its login controls to reconnect. Manage LinkedIn sessions from the LinkedIn workspace.' },{ q: 'How do I investigate a failed application?',a: 'Start with Applications and Run history. System logs provide more detail. Check platform sessions, matching preferences, daily limits, and any error message before retrying.' },{ q: 'What does dry run do?',a: 'Dry run lets you review the search and matching workflow without sending live applications. Keep it enabled while validating your preferences and profile answers.' },{ q: 'Where can I export or manage my data?',a: 'Overview offers application CSV and statistics JSON exports. Backups and Data management are in Operations. Read the confirmation text carefully before deleting records.' }].map(f => <details className="help-faq" key={f.q}>
        <summary>{f.q}</summary>
        <p>{f.a}</p>
      </details>)}</section>
    <p className="muted text-sm">Automation assists your workflow. Review your information, respect platform rules, and use the run controls to pause when needed.</p>
  </div>;
}
