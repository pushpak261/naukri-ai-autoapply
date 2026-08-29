import { useState, useEffect } from 'react';
import { FileText, Search, File } from 'lucide-react';
import { api, type LogFile, type LogContent } from '../lib/api';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function LogViewer() {
  const [files, setFiles] = useState<LogFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<LogFile | null>(null);
  const [logContent, setLogContent] = useState<LogContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [maxLines, setMaxLines] = useState(500);

  useEffect(() => {
    api.logs.list().then(r => setFiles(r.items)).finally(() => setLoading(false));
  }, []);

  const handleSelectFile = async (file: LogFile) => {
    setSelectedFile(file);
    setContentLoading(true);
    try {
      const content = await api.logs.read(file.path, maxLines);
      setLogContent(content);
    } catch {
      setLogContent(null);
    }
    setContentLoading(false);
  };

  const filteredFiles = files.filter(f =>
    f.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredContent = logContent?.content
    ? logContent.content.split('\n').filter(line =>
        !searchTerm || line.toLowerCase().includes(searchTerm.toLowerCase())
      ).join('\n')
    : '';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <FileText className="w-6 h-6 text-[#38bdf8]" />
          Log Viewer
        </h1>
        <p className="text-[#94a3b8] mt-1">Browse and search agent and terminal log files</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5 lg:col-span-1">
          <h2 className="text-sm font-medium text-[#94a3b8] mb-3">Log Files</h2>
          <div className="flex items-center gap-2 bg-[#0f172a] border border-[#334155] rounded-lg px-3 py-2 mb-3">
            <Search className="w-4 h-4 text-[#64748b]" />
            <input
              type="text"
              placeholder="Filter files..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="bg-transparent border-none outline-none text-white placeholder-[#64748b] w-full text-xs"
            />
          </div>
          <div className="space-y-1 max-h-[600px] overflow-y-auto">
            {loading ? (
              <div className="text-center py-8 text-[#64748b] text-sm">Loading...</div>
            ) : filteredFiles.length > 0 ? (
              filteredFiles.map((f) => (
                <button
                  key={f.path}
                  onClick={() => handleSelectFile(f)}
                  className={`w-full text-left p-2.5 rounded-lg transition-colors text-sm ${
                    selectedFile?.path === f.path
                      ? 'bg-[#38bdf8]/10 border border-[#38bdf8]/30'
                      : 'hover:bg-[#334155] border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <File className="w-4 h-4 text-[#64748b] shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-white text-xs truncate">{f.name}</p>
                      <p className="text-[#64748b] text-xs mt-0.5">
                        {formatSize(f.size)} &middot; {f.type}
                      </p>
                    </div>
                  </div>
                </button>
              ))
            ) : (
              <div className="text-center py-8 text-[#64748b] text-sm">No log files found</div>
            )}
          </div>
        </div>

        <div className="bg-[#1e293b] rounded-xl border border-[#334155] p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-[#94a3b8] flex items-center gap-2">
              <FileText className="w-4 h-4" />
              {selectedFile ? selectedFile.name : 'Select a file to view'}
            </h2>
            {logContent && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#64748b]">
                  Showing {logContent.showing} of {logContent.total_lines} lines
                </span>
                <select
                  value={maxLines}
                  onChange={e => { setMaxLines(Number(e.target.value)); if (selectedFile) handleSelectFile(selectedFile); }}
                  className="bg-[#0f172a] border border-[#334155] text-white text-xs rounded-lg px-2 py-1 outline-none"
                >
                  <option value={200}>200 lines</option>
                  <option value={500}>500 lines</option>
                  <option value={1000}>1000 lines</option>
                  <option value={2000}>2000 lines</option>
                  <option value={5000}>5000 lines</option>
                  <option value={50000}>50000 lines</option>
                </select>
              </div>
            )}
          </div>

          {contentLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#38bdf8]" />
            </div>
          ) : filteredContent ? (
            <pre className="bg-[#0f172a] border border-[#334155] rounded-lg p-4 text-xs font-mono text-[#94a3b8] overflow-auto max-h-[700px] whitespace-pre-wrap leading-relaxed">
              {filteredContent}
            </pre>
          ) : (
            <div className="flex items-center justify-center h-64 text-[#64748b]">
              {selectedFile ? 'Could not load log content' : 'Select a log file from the list'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
