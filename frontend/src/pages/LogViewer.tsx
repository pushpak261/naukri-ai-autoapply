import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileText, Search, File } from 'lucide-react';
import { api, type LogFile } from '../lib/api';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function LogViewer() {
  const [selectedFile, setSelectedFile] = useState<LogFile | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [maxLines, setMaxLines] = useState(500);

  const fileQuery = useQuery({ queryKey: ['log-files'], queryFn: api.logs.list });
  const contentQuery = useQuery({
    queryKey: ['log-content', selectedFile?.path, maxLines],
    queryFn: () => api.logs.read(selectedFile!.path, maxLines), enabled: !!selectedFile,
  });
  const files = fileQuery.data?.items ?? [];
  const logContent = contentQuery.data;
  const loading = fileQuery.isPending;
  const contentLoading = !!selectedFile && contentQuery.isPending;

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
        <h1 className="text-2xl font-bold text-[var(--color-text)] flex items-center gap-2">
          <FileText className="w-6 h-6 text-[var(--color-primary)]" />
          Log Viewer
        </h1>
        <p className="text-[var(--color-text-secondary)] mt-1">Browse and search agent and terminal log files</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 lg:col-span-1">
          <h2 className="text-sm font-medium text-[var(--color-text-secondary)] mb-3">Log Files</h2>
          <div className="flex items-center gap-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg px-3 py-2 mb-3">
            <Search className="w-4 h-4 text-[var(--color-text-muted)]" />
            <input
              type="text"
              placeholder="Filter files..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="bg-transparent border-none outline-none text-[var(--color-text)] placeholder-[var(--color-text-muted)] w-full text-xs"
            />
          </div>
          <div className="space-y-1 max-h-[600px] overflow-y-auto">
            {fileQuery.isError ? <div role="alert" className="notice-error"><p>{fileQuery.error.message}</p><button onClick={() => fileQuery.refetch()}>Retry log files</button></div> : loading ? (
              <div className="text-center py-8 text-[var(--color-text-muted)] text-sm">Loading...</div>
            ) : filteredFiles.length > 0 ? (
              filteredFiles.map((f) => (
                <button
                  key={f.path}
                  onClick={() => setSelectedFile(f)}
                  className={`w-full text-left p-2.5 rounded-lg transition-colors text-sm ${
                    selectedFile?.path === f.path
                      ? 'bg-[#38bdf8]/10 border border-[var(--color-primary)]/30'
                      : 'hover:bg-[var(--color-surface-hover)] border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <File className="w-4 h-4 text-[var(--color-text-muted)] shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[var(--color-text)] text-xs truncate">{f.name}</p>
                      <p className="text-[var(--color-text-muted)] text-xs mt-0.5">
                        {formatSize(f.size)} &middot; {f.type}
                      </p>
                    </div>
                  </div>
                </button>
              ))
            ) : (
              <div className="text-center py-8 text-[var(--color-text-muted)] text-sm">No log files found</div>
            )}
          </div>
        </div>

        <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-sm font-medium text-[var(--color-text-secondary)] flex items-center gap-2 min-w-0">
              <FileText className="w-4 h-4 shrink-0" />
              <span className="truncate">{selectedFile ? selectedFile.name : 'Select a file to view'}</span>
            </h2>
            {logContent && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--color-text-muted)]">
                  Showing {logContent.showing} of {logContent.total_lines} lines
                </span>
                <select
                  value={maxLines}
                  onChange={e => setMaxLines(Number(e.target.value))}
                  className="bg-[var(--color-bg)] border border-[var(--color-border)] text-[var(--color-text)] text-xs rounded-lg px-2 py-1 outline-none"
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

          {contentQuery.isError ? <div role="alert" className="notice-error"><p>{contentQuery.error.message}</p><button onClick={() => contentQuery.refetch()}>Retry log content</button></div> : contentLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[var(--color-primary)]" />
            </div>
          ) : filteredContent ? (
            <pre className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-lg p-4 text-xs font-mono text-[var(--color-text-secondary)] overflow-auto max-h-[700px] whitespace-pre-wrap break-words leading-relaxed">
              {filteredContent}
            </pre>
          ) : (
            <div className="flex items-center justify-center h-64 text-[var(--color-text-muted)]">
              {selectedFile ? (searchTerm ? 'No log lines match your search' : 'This log file is empty') : 'Select a log file from the list'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
