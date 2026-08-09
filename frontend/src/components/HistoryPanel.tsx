import { MAKE_AT_HOME, type HistoryItem } from "../types"

function formatTime(value: string): string {
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

function selectionLabel(value: string): string {
  return value === MAKE_AT_HOME ? "Make at home" : value
}

export default function HistoryPanel({ history }: { history: HistoryItem[] }) {
  return (
    <div className="mt-8 bg-slate-900 rounded-xl shadow-lg border border-slate-800 overflow-hidden">
      <div className="px-5 py-3.5 bg-slate-850 border-b border-slate-800 flex items-center justify-between">
        <h3 className="font-bold text-slate-200 flex items-center gap-2 text-xs uppercase tracking-wider">
          <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Selection &amp; Activity History
        </h3>
        <span className="text-[11px] text-slate-400 font-mono">Recent activity log</span>
      </div>

      {history.length === 0 ? (
        <div className="px-5 py-6 text-slate-500 italic text-sm text-center">
          No activity recorded yet. Make a selection to start building history.
        </div>
      ) : (
        <div className="divide-y divide-slate-800/60 max-h-80 overflow-y-auto">
          {history.map((item) => (
            <div key={item.id} className="px-5 py-2.5 flex items-center justify-between text-xs hover:bg-slate-800/40 transition-colors">
              <div className="flex items-center gap-2.5 flex-wrap">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider border ${
                    item.action.includes("Sent")
                      ? "bg-emerald-950/80 text-emerald-300 border-emerald-800/60"
                      : "bg-slate-800 text-blue-300 border-slate-700"
                  }`}
                >
                  {item.action}
                </span>
                <span className="font-bold text-slate-100">{item.kid_name}</span>
                <span className="text-slate-600">&bull;</span>
                <span className="text-slate-300 font-medium">{selectionLabel(item.selection)}</span>
                <span className="text-slate-500">for</span>
                <span className="text-slate-400 font-mono text-[11px] bg-slate-800/60 px-1.5 py-0.5 rounded">{item.menu_date}</span>
              </div>
              <div className="text-slate-500 font-mono text-[11px]">{formatTime(item.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
