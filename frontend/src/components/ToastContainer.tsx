import { useRunStore } from '@/store/runStore'

export function ToastContainer() {
  const toasts = useRunStore((s) => s.toasts)
  const removeToast = useRunStore((s) => s.removeToast)

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg ${
            t.type === 'error'
              ? 'border-destructive/50 bg-destructive/20 text-red-200'
              : t.type === 'success'
                ? 'border-emerald-500/50 bg-emerald-500/20 text-emerald-200'
                : 'border-border bg-card'
          }`}
        >
          <span>{t.message}</span>
          <button type="button" onClick={() => removeToast(t.id)} className="opacity-60 hover:opacity-100">
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
