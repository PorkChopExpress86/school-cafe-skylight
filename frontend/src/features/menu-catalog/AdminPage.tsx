import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { CatalogControls } from "./components/CatalogControls"
import { CatalogErrorState, CatalogLoadingState, CatalogStatus } from "./components/CatalogStatus"
import { CatalogItems } from "./components/CatalogItems"
import { RefreshHistory } from "./components/RefreshHistory"
import { useAdmin, useLlmCasing, useOverride, useSync } from "./useMenuCatalogApi"

export default function AdminPage() {
  const { data, isLoading, error } = useAdmin()
  const overrideMutation = useOverride()
  const syncMutation = useSync()
  const llmCasingMutation = useLlmCasing()
  const [searchQuery, setSearchQuery] = useState("")

  const filteredItems = useMemo(() => {
    if (!data?.items) return []
    if (!searchQuery.trim()) return data.items
    const normalizedQuery = searchQuery.toLowerCase()
    return data.items.filter(
      (item) =>
        item.display_description.toLowerCase().includes(normalizedQuery) ||
        item.description.toLowerCase().includes(normalizedQuery),
    )
  }, [data?.items, searchQuery])

  if (isLoading) return <CatalogLoadingState />
  if (error || !data) return <CatalogErrorState error={error} />

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-12">
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
        <CatalogStatus
          lastSuccess={data.last_success}
          syncResult={syncMutation.data}
          casingResult={llmCasingMutation.data}
        />

        <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 overflow-hidden">
          <div className="px-5 py-4 bg-slate-850 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wider">Unique Menu Items &amp; Permanent Overrides</h2>
                <span className="px-2 py-0.5 rounded-full text-xs font-extrabold bg-blue-950 text-blue-300 border border-blue-800/80">
                  {data.items.length} Unique Items
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Edit the display name for any menu item. Changing an item overrides it permanently for every date and week, past and future.
              </p>
            </div>

            <CatalogControls
              searchQuery={searchQuery}
              onSearchQueryChange={setSearchQuery}
              isApplyingCasing={llmCasingMutation.isPending}
              onApplyCasing={() => llmCasingMutation.mutate()}
            />
          </div>

          <CatalogItems
            items={filteredItems}
            totalItemCount={data.items.length}
            searchQuery={searchQuery}
            isSaving={overrideMutation.isPending}
            onSave={(original, replacement) => overrideMutation.mutate({ original, replacement })}
            onClear={(original) => overrideMutation.mutate({ original, replacement: "" })}
          />
        </section>

        <RefreshHistory attempts={data.attempts} />
      </main>
    </div>
  )
}
