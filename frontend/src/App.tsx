import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './lib/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Jobs from './pages/Jobs';
import JobDetail from './pages/JobDetail';
import Applications from './pages/Applications';
import RunLogs from './pages/RunLogs';
import Config from './pages/Config';
import Resume from './pages/Resume';
import Analytics from './pages/Analytics';
import SkillsGap from './pages/SkillsGap';
import ScamDetector from './pages/ScamDetector';
import AgentControl from './pages/AgentControl';
import CacheExplorer from './pages/CacheExplorer';
import LogViewer from './pages/LogViewer';
import Backups from './pages/Backups';
import MarketIntelligence from './pages/MarketIntelligence';
import AutoPilot from './pages/AutoPilot';
import PipelineDebugger from './pages/PipelineDebugger';
import PipelineJobs from './pages/PipelineJobs';
import Accounts from './pages/Accounts';
import WebhookManager from './pages/WebhookManager';
import LinkedIn from './pages/LinkedIn';
import ClearData from './pages/ClearData';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/market-intelligence" element={<MarketIntelligence />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/skills-gap" element={<SkillsGap />} />
            <Route path="/autopilot" element={<AutoPilot />} />
            <Route path="/pipeline-debugger" element={<PipelineDebugger />} />
            <Route path="/pipeline-jobs" element={<PipelineJobs />} />
            <Route path="/scam-detector" element={<ScamDetector />} />
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
