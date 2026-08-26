import type { SyncAttempt } from "../types"

export interface RefreshHistoryProps {
  attempts: SyncAttempt[]
}

export function RefreshHistory({ attempts }: RefreshHistoryProps) {
  return (
    <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 overflow-hidden">
      <div className="px-5 py-3.5 bg-slate-850 border-b border-slate-800">
        <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Sync Log History</h2>
        <p className="text-xs text-slate-400 mt-0.5">Most recent first. The running app makes one scheduled Sunday attempt at 3:00 AM Central Time.</p>
      </div>
      {attempts.length === 0 ? (
        <div className="px-5 py-6 text-sm text-slate-500 italic text-center">No sync attempts recorded yet.</div>
      ) : (
        <div className="divide-y divide-slate-800/60 max-h-80 overflow-y-auto">
          {attempts.map((attempt, index) => (
            <div key={index} className="px-5 py-2.5 flex items-center justify-between text-xs hover:bg-slate-800/40 transition-colors">
              <div className="flex items-center gap-3">
                {attempt.succeeded ? (
                  <>
                    <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-emerald-950/80 text-emerald-300 border border-emerald-800/60">
                      OK
                    </span>
                    <span className="text-slate-200 font-medium">{attempt.weeks_fetched} weeks / {attempt.items_stored} items</span>
                  </>
                ) : (
                  <>
                    <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-red-950/80 text-red-300 border border-red-800/60">
                      FAIL
                    </span>
                    <span className="text-red-400 font-medium">{attempt.error ?? "Unknown error"}</span>
                  </>
                )}
              </div>
              <div className="text-slate-500 font-mono text-[11px]">{attempt.attempted_at}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
