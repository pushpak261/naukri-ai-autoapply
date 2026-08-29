import { lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './lib/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Register from './pages/Register';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const MarketIntel = lazy(() => import('./pages/MarketIntelligence'));
const Analytics = lazy(() => import('./pages/Analytics'));
const SkillsGap = lazy(() => import('./pages/SkillsGap'));
const AutoPilot = lazy(() => import('./pages/AutoPilot'));
const ScamDetector = lazy(() => import('./pages/ScamDetector'));
const JobInspector = lazy(() => import('./pages/JobInspector'));
const AgentControl = lazy(() => import('./pages/AgentControl'));
const LinkedIn = lazy(() => import('./pages/LinkedIn'));
const Jobs = lazy(() => import('./pages/Jobs'));
const JobDetail = lazy(() => import('./pages/JobDetail'));
const Applications = lazy(() => import('./pages/Applications'));
const RunLogs = lazy(() => import('./pages/RunLogs'));
const CacheExplorer = lazy(() => import('./pages/CacheExplorer'));
const LogViewer = lazy(() => import('./pages/LogViewer'));
const Backups = lazy(() => import('./pages/Backups'));
const Config = lazy(() => import('./pages/Config'));
const Resume = lazy(() => import('./pages/Resume'));
const Accounts = lazy(() => import('./pages/Accounts'));
const WebhookManager = lazy(() => import('./pages/WebhookManager'));
const ClearData = lazy(() => import('./pages/ClearData'));

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/market-intelligence" element={<MarketIntel />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/skills-gap" element={<SkillsGap />} />
            <Route path="/autopilot" element={<AutoPilot />} />
            <Route path="/scam-detector" element={<ScamDetector />} />
            <Route path="/job-inspector" element={<JobInspector />} />
            <Route path="/agent-control" element={<AgentControl />} />

            <Route path="/linkedin" element={<LinkedIn />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/applications" element={<Applications />} />
            <Route path="/run-logs" element={<RunLogs />} />
            <Route path="/cache-explorer" element={<CacheExplorer />} />
            <Route path="/log-viewer" element={<LogViewer />} />
            <Route path="/backups" element={<Backups />} />
            <Route path="/config" element={<Config />} />
            <Route path="/resume" element={<Resume />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/webhooks" element={<WebhookManager />} />
            <Route path="/clear-data" element={<ClearData />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
