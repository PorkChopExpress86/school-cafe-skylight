import { useState } from "react"
import { Link } from "react-router-dom"
import { useAdmin, useOverride, useSync } from "../hooks/useApi"

export default function AdminPage() {
  const { data, isLoading, error } = useAdmin()
  const overrideMutation = useOverride()
  const syncMutation = useSync()
  const [edits, setEdits] = useState<Record<string, string>>({})

  if (isLoading) {
    return <div className="max-w-5xl mx-auto px-4 py-6 text-slate-500">Loading admin...</div>
  }

  if (error || !data) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="mb-4 p-3 rounded-md bg-amber-100 text-amber-800 border border-amber-300 text-sm">
          Could not load admin data. {error instanceof Error ? error.message : ""}
        </div>
      </div>
    )
  }

  const handleSave = (original: string) => {
    const replacement = (edits[original] ?? "").trim()
    overrideMutation.mutate({ original, replacement })
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-700">Menu sync admin</h1>
          <p className="text-sm text-slate-400 mt-1">Manage menu item display text and view sync history.</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/"
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-slate-200 text-slate-700 hover:bg-slate-300"
          >
            &larr; Dashboard
          </Link>
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {syncMutation.isPending ? "Syncing..." : "Sync now"}
          </button>
        </div>
      </header>

      {syncMutation.data && (
        <div
          className={`p-3 rounded-md border text-sm ${
            syncMutation.data.ok
              ? "bg-emerald-100 text-emerald-800 border-emerald-300"
              : "bg-amber-100 text-amber-800 border-amber-300"
          }`}
        >
          {syncMutation.data.message}
        </div>
      )}

      {/* Last sync status */}
      <section className="bg-white rounded-lg shadow-sm border border-slate-200 p-5">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Last sync</h2>
        {data.last_success ? (
          <div className="flex items-center gap-3">
            <span className="px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider bg-emerald-100 text-emerald-800 border border-emerald-200">
              Success
            </span>
            <span className="text-sm text-slate-700">
              {data.last_success.attempted_at} &mdash; {data.last_success.items_stored} items across{" "}
              {data.last_success.weeks_fetched} weeks
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider bg-red-100 text-red-800 border border-red-200">
              No successful sync yet
            </span>
          </div>
        )}
      </section>

      {/* Sync history */}
      <section className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-200">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Sync history</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Most recent first. Sunday cron + 2-hour retries for 48 hours on failure.
          </p>
        </div>
        {data.attempts.length === 0 ? (
          <div className="px-5 py-6 text-sm text-slate-400 italic text-center">
            No sync attempts yet. Run the Sunday cron or click "Sync now".
          </div>
        ) : (
          <div className="divide-y divide-slate-100 max-h-96 overflow-y-auto">
            {data.attempts.map((a, i) => (
              <div key={i} className="px-5 py-2.5 flex items-center justify-between text-xs hover:bg-slate-50">
                <div className="flex items-center gap-3">
                  {a.succeeded ? (
                    <>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-emerald-100 text-emerald-800 border border-emerald-200">
                        OK
                      </span>
                      <span className="text-slate-700 font-medium">
                        {a.weeks_fetched} weeks / {a.items_stored} items
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-red-100 text-red-800 border border-red-200">
                        FAIL
                      </span>
                      <span className="text-red-700 font-medium">{a.error ?? "???"}</span>
                    </>
                  )}
                </div>
                <div className="text-slate-400 font-mono text-[11px]">{a.attempted_at}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Cached menu items with override editing */}
      <section className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-200">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wider">Cached menu items</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Edit the display text for any item. Overrides persist forever and apply to every week, past and
            future. Leave the replacement blank to clear.
          </p>
        </div>

        {data.weeks.length === 0 ? (
          <div className="px-5 py-6 text-sm text-slate-400 italic text-center">
            No menu items cached yet. Run a sync to fetch the next 4 weeks.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {data.weeks.map((weekStart) => (
              <div key={weekStart} className="p-5">
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Week of {weekStart}
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-400 uppercase tracking-wider">
                      <th className="text-left font-normal pb-2">Date</th>
                      <th className="text-left font-normal pb-2">Display text</th>
                      <th className="text-left font-normal pb-2">Original</th>
                      <th className="text-left font-normal pb-2">Edit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items
                      .filter((item) => item.week_start === weekStart)
                      .map((item) => (
                        <tr key={`${item.menu_date}-${item.description}`} className="border-t border-slate-50">
                          <td className="py-1.5 text-slate-500 font-mono text-xs">{item.menu_date}</td>
                          <td className="py-1.5 text-slate-800 font-medium">
                            {item.display_description}
                            {item.display_description !== item.description && (
                              <span className="ml-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-amber-100 text-amber-800 border border-amber-200">
                                overridden
                              </span>
                            )}
                          </td>
                          <td className="py-1.5 text-slate-400 text-xs">{item.description}</td>
                          <td className="py-1.5">
                            <div className="flex items-center gap-1">
                              <input
                                type="text"
                                value={edits[item.description] ?? item.display_description}
                                onChange={(e) =>
                                  setEdits((prev) => ({ ...prev, [item.description]: e.target.value }))
                                }
                                className="px-2 py-1 text-xs rounded border border-slate-300 focus:outline-none focus:ring-1 focus:ring-slate-500 w-48"
                                placeholder="Display text"
                              />
                              <button
                                onClick={() => handleSave(item.description)}
                                disabled={overrideMutation.isPending}
                                className="px-2 py-1 text-xs font-medium rounded bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50"
                              >
                                Save
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
