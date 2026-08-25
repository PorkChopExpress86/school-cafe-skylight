import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useAdmin, useLlmCasing, useOverride, useSync } from "../hooks/useApi"

export default function AdminPage() {
  const { data, isLoading, error } = useAdmin()
  const overrideMutation = useOverride()
  const syncMutation = useSync()
  const llmCasingMutation = useLlmCasing()
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [searchQuery, setSearchQuery] = useState("")

  const filteredItems = useMemo(() => {
    if (!data?.items) return []
    if (!searchQuery.trim()) return data.items
    const q = searchQuery.toLowerCase()
    return data.items.filter(
      (item) =>
        item.display_description.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q)
    )
  }, [data?.items, searchQuery])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6 text-slate-300">
        <div className="flex items-center gap-3 bg-slate-900 px-6 py-4 rounded-xl border border-slate-800 shadow-xl backdrop-blur">
          <div className="w-5 h-5 border-2 border-red-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="font-medium text-slate-200">Loading Menu Sync Admin...</span>
        </div>
      </div>
    )
  }

  if (error || !data) {
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

  const handleSave = (original: string) => {
    const replacement = (edits[original] ?? "").trim()
    overrideMutation.mutate({ original, replacement })
  }

  const handleClear = (original: string) => {
    setEdits((prev) => ({ ...prev, [original]: "" }))
    overrideMutation.mutate({ original, replacement: "" })
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-12">
      {/* Top Patriot Accent Bar */}
      <div className="h-1.5 w-full bg-gradient-to-r from-blue-700 via-red-600 to-amber-400"></div>

      <header className="bg-slate-900/90 border-b border-slate-800 sticky top-0 z-30 backdrop-blur-md shadow-md">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-900 to-red-900 border border-red-500/30 flex items-center justify-center text-amber-400 text-lg font-bold shadow-inner">
              ⚙️
            </div>
            <div>
              <h1 className="text-lg font-extrabold text-white tracking-tight">Menu Sync Admin</h1>
              <p className="text-xs text-slate-400">Elementary School • School Menu</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link
              to="/"
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 transition-all shadow-sm"
            >
              &larr; Dashboard
            </Link>
            <button
              onClick={() => llmCasingMutation.mutate()}
              disabled={llmCasingMutation.isPending}
              className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white border border-blue-500/30 transition-all shadow-sm active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
            >
              {llmCasingMutation.isPending ? (
                <>
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  <span>Running AI Casing...</span>
                </>
              ) : (
                <>
                  <span>🤖</span>
                  <span>Auto-Case All (Gemini AI)</span>
                </>
              )}
            </button>
            <button
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
              className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white border border-red-500/30 transition-all shadow-sm active:scale-95 disabled:opacity-50"
            >
              {syncMutation.isPending ? "Syncing..." : "Sync now"}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 pt-6 space-y-6">
        {llmCasingMutation.data && (
          <div
            className={`p-4 rounded-xl border text-sm flex items-center gap-3 shadow-md ${
              llmCasingMutation.data.ok
                ? "bg-blue-950/80 text-blue-200 border-blue-800/80"
                : "bg-amber-950/80 text-amber-200 border-amber-800/80"
            }`}
          >
            <span>🤖</span>
            <div>{llmCasingMutation.data.message}</div>
          </div>
        )}

        {syncMutation.data && (
          <div
            className={`p-4 rounded-xl border text-sm flex items-center gap-3 shadow-md ${
              syncMutation.data.ok
                ? "bg-emerald-950/80 text-emerald-200 border-emerald-800/80"
                : "bg-amber-950/80 text-amber-200 border-amber-800/80"
            }`}
          >
            <span>{syncMutation.data.ok ? "✅" : "⚠️"}</span>
            <div>{syncMutation.data.message}</div>
          </div>
        )}

        {/* Last sync status */}
        <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 p-5">
          <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Last Sync Status</h2>
          {data.last_success ? (
            <div className="flex items-center gap-3">
              <span className="px-2.5 py-1 rounded-md text-xs font-extrabold uppercase tracking-wider bg-emerald-950/80 text-emerald-300 border border-emerald-800/60">
                Success
              </span>
              <span className="text-sm text-slate-200 font-medium">
                {data.last_success.attempted_at} &mdash; {data.last_success.items_stored} items stored across{" "}
                {data.last_success.weeks_fetched} weeks
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

        {/* Unique Cached Menu Items & Display Overrides */}
        <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 overflow-hidden">
          <div className="px-5 py-4 bg-slate-850 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
                  Unique Menu Items &amp; Permanent Overrides
                </h2>
                <span className="px-2 py-0.5 rounded-full text-xs font-extrabold bg-blue-950 text-blue-300 border border-blue-800/80">
                  {data.items.length} Unique Items
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Edit the display name for any menu item. Changing an item overrides it permanently for every date and week, past and future.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-2.5 w-full md:w-auto">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search items..."
                className="w-full sm:w-48 px-3 py-1.5 text-xs rounded-lg bg-slate-800 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500"
              />
              <button
                type="button"
                onClick={() => llmCasingMutation.mutate()}
                disabled={llmCasingMutation.isPending}
                className="w-full sm:w-auto px-3.5 py-1.5 text-xs font-bold rounded-lg bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white border border-blue-500/30 transition-all shadow-sm active:scale-95 disabled:opacity-50 whitespace-nowrap flex items-center justify-center gap-1.5"
              >
                {llmCasingMutation.isPending ? (
                  <>
                    <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    <span>Running agy AI Casing...</span>
                  </>
                ) : (
                  <>
                    <span>🤖</span>
                    <span>Auto-Case All Items (agy AI)</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {data.items.length === 0 ? (
            <div className="px-5 py-8 text-sm text-slate-500 italic text-center">
              No menu items cached yet. Click "Sync now" above to fetch the school menu.
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="px-5 py-8 text-sm text-slate-500 italic text-center">
              No menu items match "{searchQuery}".
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-400 uppercase tracking-wider border-b border-slate-800 bg-slate-900/80">
                    <th className="text-left font-semibold py-3 px-5">Active Display Name</th>
                    <th className="text-left font-semibold py-3 px-5">Original Source Description</th>
                    <th className="text-left font-semibold py-3 px-5">Permanent Override Edit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredItems.map((item) => {
                    const isOverridden = item.display_description !== item.description
                    const currentInput = edits[item.description] ?? item.display_description

                    return (
                      <tr key={item.description} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-5 font-semibold text-slate-100">
                          <div className="flex items-center gap-2">
                            <span>{item.display_description}</span>
                            {isOverridden ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-amber-950/80 text-amber-300 border border-amber-800/60 shadow-sm">
                                Overridden
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-slate-800 text-slate-400 border border-slate-700">
                                Original
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="py-3 px-5 text-slate-400 font-mono text-xs">
                          {item.description}
                        </td>

                        <td className="py-3 px-5">
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={currentInput}
                              onChange={(e) =>
                                setEdits((prev) => ({ ...prev, [item.description]: e.target.value }))
                              }
                              className="px-3 py-1.5 text-xs rounded-lg bg-slate-800 border border-slate-700 text-slate-100 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500 w-56 font-medium"
                              placeholder="Display name"
                            />
                            <button
                              onClick={() => handleSave(item.description)}
                              disabled={overrideMutation.isPending}
                              className="px-3 py-1.5 text-xs font-bold rounded-lg bg-blue-600 hover:bg-blue-500 text-white border border-blue-500/30 transition-all active:scale-95 disabled:opacity-50 shadow-sm"
                            >
                              Save
                            </button>
                            {isOverridden && (
                              <button
                                onClick={() => handleClear(item.description)}
                                disabled={overrideMutation.isPending}
                                className="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
                                title="Reset to original description"
                              >
                                Reset
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Sync History */}
        <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 overflow-hidden">
          <div className="px-5 py-3.5 bg-slate-850 border-b border-slate-800">
            <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Sync Log History</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Most recent first. The running app makes one scheduled Sunday attempt at 3:00 AM Central Time.
            </p>
          </div>
          {data.attempts.length === 0 ? (
            <div className="px-5 py-6 text-sm text-slate-500 italic text-center">
              No sync attempts recorded yet.
            </div>
          ) : (
            <div className="divide-y divide-slate-800/60 max-h-80 overflow-y-auto">
              {data.attempts.map((a, i) => (
                <div key={i} className="px-5 py-2.5 flex items-center justify-between text-xs hover:bg-slate-800/40 transition-colors">
                  <div className="flex items-center gap-3">
                    {a.succeeded ? (
                      <>
                        <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-emerald-950/80 text-emerald-300 border border-emerald-800/60">
                          OK
                        </span>
                        <span className="text-slate-200 font-medium">
                          {a.weeks_fetched} weeks / {a.items_stored} items
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-red-950/80 text-red-300 border border-red-800/60">
                          FAIL
                        </span>
                        <span className="text-red-400 font-medium">{a.error ?? "Unknown error"}</span>
                      </>
                    )}
                  </div>
                  <div className="text-slate-500 font-mono text-[11px]">{a.attempted_at}</div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
