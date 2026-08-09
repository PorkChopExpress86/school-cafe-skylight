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
    <div className="mt-8 bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
      <div className="px-5 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <h3 className="font-semibold text-slate-700 flex items-center gap-2 text-sm uppercase tracking-wider">
          <svg className="w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Selection &amp; Activity History
        </h3>
        <span className="text-xs text-slate-400">Recent events</span>
      </div>

      {history.length === 0 ? (
        <div className="px-5 py-4 text-slate-400 italic text-sm">
          No activity recorded yet. Make a selection to start building history.
        </div>
      ) : (
        <div className="divide-y divide-slate-100 max-h-80 overflow-y-auto">
          {history.map((item) => (
            <div key={item.id} className="px-5 py-2.5 flex items-center justify-between text-xs hover:bg-slate-50 transition-colors">
              <div className="flex items-center gap-3">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border ${
                    item.action.includes("Sent")
                      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
                      : "bg-slate-100 text-slate-700 border-slate-200"
                  }`}
                >
                  {item.action}
                </span>
                <span className="font-semibold text-slate-800">{item.kid_name}</span>
                <span className="text-slate-400">&bull;</span>
                <span className="text-slate-700 font-medium">{selectionLabel(item.selection)}</span>
                <span className="text-slate-400">for</span>
                <span className="text-slate-500 font-medium">{item.menu_date}</span>
              </div>
              <div className="text-slate-400 font-mono text-[11px]">{formatTime(item.created_at)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
