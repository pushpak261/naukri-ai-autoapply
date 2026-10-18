import { type ReactNode,useEffect } from 'react';
import { Command,ArrowRight,FileText,ScanSearch,Send,Sun,Moon } from 'lucide-react';
import { brand } from '../lib/brand';
import { useTheme } from '../lib/ThemeContext';
export default function AuthFrame({ children,title,subtitle }: {
  children: ReactNode;
  title: string;
  subtitle: string;
}) {
  const { theme,toggle }=useTheme();
  useEffect(() => { document.title=`${title} · ${brand.name}`; },[title]);
  return <main className="auth-layout">
    <section className="auth-story">
      <div className="auth-wordmark">
        <Command size={27} />{brand.name}</div>
      <div className="auth-pitch">
        <p className="eyebrow">A MORE INTENTIONAL JOB SEARCH</p>
        <h1>Your next chapter.<br />
          <span>All in one place.</span>
        </h1>
        <p>Bring your profile, opportunities, and application workflow into one focused workspace.</p>
        <div className="auth-journey">{[{ icon: FileText,title: 'Build your foundation',text: 'Your resume and career preferences.' },{ icon: ScanSearch,title: 'Find your direction',text: 'Discover roles and review your matches.' },{ icon: Send,title: 'Move with confidence',text: 'Assist applications and track every run.' }].map((item,i) => <div key={item.title}>
          <span className="journey-icon">
            <item.icon size={20} />
          </span>
          <section>
            <small>0{i+1}</small>
            <strong>{item.title}</strong>
            <p>{item.text}</p>
          </section>
        </div>)}</div>
      </div>
      <footer>Naukri & LinkedIn workflows <ArrowRight size={16} />
        <span>Your search. Your decisions.</span>
      </footer>
    </section>
    <section className="auth-form-side">
      <button className="auth-theme" aria-label={`Switch to ${theme==='dark'? 'light':'dark'} theme`} onClick={toggle}>{theme==='dark'? <Sun size={20} />:<Moon size={20} />}</button>
      <div className="auth-form-wrap">
        <div className="auth-mobile-brand">
          <Command size={22} />{brand.name}</div>
        <p className="eyebrow">YOUR CAREER WORKSPACE</p>
        <h2>{title}</h2>
        <p className="auth-subtitle">{subtitle}</p>{children}
        </div>
      <p className="auth-bottom">{brand.tagline}</p>
    </section>
  </main>;
}
