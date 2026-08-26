import type { CasingResponse, SyncAttempt, SyncResponse } from "../types"

export interface CatalogLoadingStateProps {
  message?: string
}

export function CatalogLoadingState({ message = "Loading Menu Sync Admin..." }: CatalogLoadingStateProps) {
  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 text-slate-300">
      <div className="flex items-center gap-3 bg-slate-900 px-6 py-4 rounded-xl border border-slate-800 shadow-xl backdrop-blur">
        <div className="w-5 h-5 border-2 border-red-500 border-t-transparent rounded-full animate-spin"></div>
        <span className="font-medium text-slate-200">{message}</span>
      </div>
    </div>
  )
}

export interface CatalogErrorStateProps {
  error: unknown
}

export function CatalogErrorState({ error }: CatalogErrorStateProps) {
  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="p-4 rounded-xl bg-red-950/80 text-red-200 border border-red-800/80 shadow-lg text-sm flex items-center gap-3">
        <span className="text-xl">⚠️</span>
        <div>
          <strong className="font-semibold text-red-100">Could not load admin data.</strong>
          <p className="mt-0.5 opacity-90">{error instanceof Error ? error.message : "Network error"}</p>
        </div>
      </div>
    </div>
  )
}

export interface CatalogStatusProps {
  lastSuccess: SyncAttempt | null
  syncResult?: SyncResponse
  casingResult?: CasingResponse
}

export function CatalogStatus({ lastSuccess, syncResult, casingResult }: CatalogStatusProps) {
  return (
    <>
      {casingResult && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-center gap-3 shadow-md ${
            casingResult.ok
              ? "bg-blue-950/80 text-blue-200 border-blue-800/80"
              : "bg-amber-950/80 text-amber-200 border-amber-800/80"
          }`}
        >
          <span>🤖</span>
          <div>{casingResult.message}</div>
        </div>
      )}

      {syncResult && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-center gap-3 shadow-md ${
            syncResult.ok
              ? "bg-emerald-950/80 text-emerald-200 border-emerald-800/80"
              : "bg-amber-950/80 text-amber-200 border-amber-800/80"
          }`}
        >
          <span>{syncResult.ok ? "✅" : "⚠️"}</span>
          <div>{syncResult.message}</div>
        </div>
      )}

      <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 p-5">
        <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Last Sync Status</h2>
        {lastSuccess ? (
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-1 rounded-md text-xs font-extrabold uppercase tracking-wider bg-emerald-950/80 text-emerald-300 border border-emerald-800/60">
              Success
            </span>
            <span className="text-sm text-slate-200 font-medium">
              {lastSuccess.attempted_at} &mdash; {lastSuccess.items_stored} items stored across {lastSuccess.weeks_fetched} weeks
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-1 rounded-md text-xs font-extrabold uppercase tracking-wider bg-red-950/80 text-red-300 border border-red-800/60">
              No successful sync yet
            </span>
          </div>
        )}
      </section>
    </>
  )
}
