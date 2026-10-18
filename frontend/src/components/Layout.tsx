import { Suspense,useEffect,useState,useRef } from 'react';
import { Link,NavLink,Outlet,useLocation,useNavigate } from 'react-router-dom';
import { LayoutDashboard,Briefcase,FileCheck,History,Settings,User,BarChart3,Radar,ShieldAlert,Bot,Database,FileText,HardDrive,Sun,Moon,Zap,LineChart,LogOut,Users,Webhook,Globe,Trash2,Filter,Menu,X,ArrowUpRight,CircleHelp,Search,Command,Sparkles } from 'lucide-react';
import { useTheme } from '../lib/ThemeContext';
import { useAuth } from '../lib/AuthContext';
import { brand } from '../lib/brand';
import AIAdvisor from './AIAdvisor';
const groups=[
  { label: 'WORKSPACE',items: [{ to: '/',icon: LayoutDashboard,label: 'Overview',end: true },{ to: '/jobs',icon: Briefcase,label: 'Discover jobs' },{ to: '/applications',icon: FileCheck,label: 'Applications' },{ to: '/agent-control',icon: Bot,label: 'Command center' }] },
  { label: 'INTELLIGENCE',items: [{ to: '/copilot',icon: Sparkles,label: 'Opportunity Copilot' },{ to: '/analytics',icon: BarChart3,label: 'Analytics' },{ to: '/market-intelligence',icon: LineChart,label: 'Market intelligence' },{ to: '/skills-gap',icon: Radar,label: 'Skills gap' },{ to: '/job-inspector',icon: Filter,label: 'Job inspector' },{ to: '/scam-detector',icon: ShieldAlert,label: 'Scam detector' }] },
  { label: 'YOUR SETUP',items: [{ to: '/resume',icon: User,label: 'Resume & profile' },{ to: '/accounts',icon: Users,label: 'Connected accounts' },{ to: '/linkedin',icon: Globe,label: 'LinkedIn workspace' },{ to: '/config',icon: Settings,label: 'Preferences' },{ to: '/autopilot',icon: Zap,label: 'Auto-pilot' },{ to: '/help',icon: CircleHelp,label: 'Getting started' }] },
  { label: 'OPERATIONS',items: [{ to: '/run-logs',icon: History,label: 'Run history' },{ to: '/log-viewer',icon: FileText,label: 'System logs' },{ to: '/cache-explorer',icon: Database,label: 'Match cache' },{ to: '/backups',icon: HardDrive,label: 'Backups' },{ to: '/webhooks',icon: Webhook,label: 'Webhooks' },{ to: '/clear-data',icon: Trash2,label: 'Data management' }] },
];
export default function Layout() {
  const { theme,toggle }=useTheme();
  const { user,logout }=useAuth();
  const navigate=useNavigate();
  const location=useLocation();
  const [open,setOpen]=useState(false);
  const [filter,setFilter]=useState('');
  const menuButton=useRef<HTMLButtonElement>(null);
  const drawer=useRef<HTMLElement>(null);
  const title=groups.flatMap(g => g.items).find(i => i.to===location.pathname)?.label||(location.pathname.startsWith('/jobs/')? 'Job details':'Workspace');
  useEffect(() => { setOpen(false); setFilter(''); document.title=`${title} · ${brand.name}`; },[location.pathname,title]);
  useEffect(() => {
    if(!open)
      return;
    drawer.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const handler=(e: KeyboardEvent) => {
      if(e.key==='Escape') {
        setOpen(false);
        menuButton.current?.focus();
      }
      if(e.key==='Tab') {
        const nodes=drawer.current?.querySelectorAll<HTMLElement>('a, button, input');
        if(!nodes?.length)
          return;
        const first=nodes[0],last=nodes[nodes.length-1];
        if(e.shiftKey&&document.activeElement===first) {
          e.preventDefault();
          last.focus();
        }
        else if(!e.shiftKey&&document.activeElement===last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown',handler);
    return () => document.removeEventListener('keydown',handler);
  },[open]);
  const sidebar=<>
    <Link to="/" className="workspace-brand">
      <span className="brand-symbol">
        <Command size={22} />
      </span>
      <span>{brand.name}<small>CAREER WORKSPACE</small>
      </span>
    </Link>
    <label className="nav-search">
      <Search size={15} />
      <input aria-label="Find a workspace page" placeholder="Find a page…" value={filter} onChange={e => setFilter(e.target.value)} />
    </label>
    <nav className="workspace-nav" aria-label="Main navigation">{groups.map(g => {
      const items=g.items.filter(i => i.label.toLowerCase().includes(filter.toLowerCase()));
      return items.length>0&&<section key={g.label}>
        <p>{g.label}</p>{items.map(i => <NavLink key={i.to} to={i.to} end={'end' in i? i.end:false} className={({ isActive }) => `workspace-nav-link ${isActive? 'active':''}`}>
          <i.icon size={17} />{i.label}</NavLink>)}</section>;
    })}{filter&&!groups.some(g => g.items.some(i => i.label.toLowerCase().includes(filter.toLowerCase())))&&<p className="muted p-3 text-sm">No pages found.</p>}</nav>
    <div className="workspace-user">
      <span className="user-avatar">{user?.email.slice(0,1).toUpperCase()||'A'}</span>
      <div>
        <strong>Personal workspace</strong>
        <span title={user?.email}>{user?.email}</span>
      </div>
      <button aria-label="Sign out" title="Sign out" onClick={async () => { await logout(); navigate('/login',{ replace: true }); }}>
        <LogOut size={17} />
      </button>
    </div>
  </>;
  return <div className="workspace-shell">
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="workspace-sidebar">{sidebar}</aside>{open&&<div className="drawer-wrap">
      <div className="drawer-overlay" onClick={() => { setOpen(false); menuButton.current?.focus(); }} />
      <aside ref={drawer} className="workspace-drawer" role="dialog" aria-modal="true" aria-label="Navigation">
        <button className="drawer-close" aria-label="Close navigation" onClick={() => { setOpen(false); menuButton.current?.focus(); }}>
          <X size={20} />
        </button>{sidebar}</aside>
    </div>}<div className="workspace-body">
      <header className="workspace-header">
        <div className="flex items-center gap-3 min-w-0">
          <button ref={menuButton} className="mobile-menu" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(true)}>
            <Menu size={21} />
          </button>
          <span className="header-workspace">Workspace <span>/</span>
          </span>
          <strong className="truncate">{title}</strong>
        </div>
        <div className="header-actions">
          <Link to="/help" className="header-help" aria-label="Quick guide">
            <CircleHelp size={16} />
            <span>Quick guide</span>
          </Link>
          <button onClick={toggle} aria-label={`Switch to ${theme==='dark'? 'light':'dark'} theme`}>{theme==='dark'? <Sun size={18} />:<Moon size={18} />}</button>
          <Link to="/agent-control" className="header-command">Command center <ArrowUpRight size={14} />
          </Link>
        </div>
      </header>
      <main id="main-content" className="workspace-main" tabIndex={-1}>
        <div className="workspace-content">
          <Suspense fallback={<div className="workspace-loading" role="status">
            <span className="loading-ring" />Loading your workspace…</div>}>
            <Outlet />
            <AIAdvisor />
          </Suspense>
        </div>
      </main>
    </div>
  </div>;
}
