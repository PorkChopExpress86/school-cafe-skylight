import { useState } from "react"
import { Link } from "react-router-dom"
import DaySection from "./DaySection"
import HistoryPanel from "./HistoryPanel"
import { useWeek } from "./usePlannerApi"
import { usePlannerInteraction } from "./usePlannerInteraction"

export default function WeekPage() {
  const [date, setDate] = useState<string | undefined>(undefined)
  const { data, isLoading, error } = useWeek(date)
  const interaction = usePlannerInteraction()

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-6 text-slate-300">
        <div className="flex items-center gap-3 bg-slate-800/80 px-6 py-4 rounded-xl border border-slate-700 shadow-xl backdrop-blur">
          <div className="w-5 h-5 border-2 border-red-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="font-medium text-slate-200">Loading Post Elementary Menu...</span>
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
            <strong className="font-semibold text-red-100">Could not load the school menu.</strong>
            <p className="mt-0.5 opacity-90">{error instanceof Error ? error.message : "Network error"}</p>
          </div>
        </div>
      </div>
    )
  }

  const weekStart = data.week.length > 0 ? data.week[0].date : data.ref
  const weekStartLabel = new Date(`${weekStart}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-12">
      {/* Top Patriot Decorative Accent Line */}
      <div className="h-1.5 w-full bg-gradient-to-r from-blue-700 via-red-600 to-amber-400"></div>

      {/* Main Header / Banner */}
      <header className="bg-slate-900/90 border-b border-slate-800 sticky top-0 z-30 backdrop-blur-md shadow-md">
        <div className="max-w-5xl mx-auto px-4 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-blue-900 to-red-900 border border-red-500/30 flex items-center justify-center shadow-inner text-amber-400 text-xl font-bold">
              ⭐️
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold tracking-widest text-red-500 uppercase px-2 py-0.5 bg-red-950/60 border border-red-800/40 rounded">
                  Elementary School
                </span>
                <span className="text-xs text-slate-400 font-mono">School Menu</span>
              </div>
              <h1 className="text-xl font-extrabold text-white tracking-tight mt-0.5">
                School Lunch Planner
              </h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between md:justify-end gap-3">
            <span className="text-xs text-slate-400 hidden lg:inline font-medium">
              Week of <strong className="text-slate-200">{weekStartLabel}</strong>
            </span>
            <button
              onClick={() => interaction.week.onPublication(data.ref)}
              disabled={interaction.week.isPublishing}
              className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white border border-red-500/40 shadow-sm active:scale-95 disabled:opacity-50 flex items-center gap-1.5"
            >
              {interaction.week.isPublishing ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  <span>Sending Week...</span>
                </>
              ) : (
                <>
                  <span>🗓️</span>
                  <span>Send Week to Skylight</span>
                </>
              )}
            </button>
            <nav className="flex items-center gap-2">
              <button
                onClick={() => setDate(data.prev_week)}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-all shadow-sm active:scale-95"
              >
                &larr; Prev
              </button>
              <button
                onClick={() => setDate(undefined)}
                className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 border border-blue-500 text-white hover:bg-blue-500 transition-all shadow-sm active:scale-95"
              >
                This week
              </button>
              <button
                onClick={() => setDate(data.next_week)}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-800 border border-slate-700 text-slate-200 hover:bg-slate-700 hover:border-slate-600 transition-all shadow-sm active:scale-95"
              >
                Next &rarr;
              </button>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 pt-6 space-y-6">
        {interaction.week.result && (
          <div
            className={`p-4 rounded-xl border text-sm flex items-center gap-3 shadow-md ${
              interaction.week.result.ok
                ? "bg-emerald-950/80 text-emerald-200 border-emerald-800/80"
                : "bg-amber-950/80 text-amber-200 border-amber-800/80"
            }`}
          >
            <span>{interaction.week.result.ok ? "✅" : "⚠️"}</span>
            <div>{interaction.week.result.message}</div>
          </div>
        )}

        {!data.school_cfg && (
          <div className="p-4 rounded-xl bg-amber-950/70 text-amber-200 border border-amber-800/60 text-sm shadow-md flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <div>
              Set <code className="bg-amber-900/60 px-1.5 py-0.5 rounded text-amber-100 font-mono text-xs">SCHOOL_ID</code> in{" "}
              <code className="bg-amber-900/60 px-1.5 py-0.5 rounded text-amber-100 font-mono text-xs">.env</code> to fetch the weekly menu from CFISD.
            </div>
          </div>
        )}
        {data.menu_error && (
          <div className="p-4 rounded-xl bg-amber-950/70 text-amber-200 border border-amber-800/60 text-sm shadow-md flex items-center gap-3">
            <span className="text-xl">⚠️</span>
            <div>Could not fetch menu: {data.menu_error}</div>
          </div>
        )}

        <div className="space-y-5">
          {data.week.map((day) => {
            const daySelections = data.selections[day.date] ?? {}
            const total = data.day_totals[day.date] ?? 0
            const sentCount = data.day_sent[day.date] ?? 0
            return (
              <DaySection
                key={day.date}
                day={day}
                kids={data.kids}
                selections={daySelections}
                total={total}
                sentCount={sentCount}
                interaction={interaction.forDate(day.date)}
              />
            )
          })}
        </div>

        <HistoryPanel history={data.history} />

        <footer className="mt-8 pt-6 border-t border-slate-800 text-xs text-slate-400 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
            <span>School Lunch Planner ⭐️</span>
          </div>
          <div className="flex items-center gap-4">
            <details className="relative">
              <summary className="cursor-pointer hover:text-slate-200 transition-colors">Server Config</summary>
              <pre className="absolute right-0 bottom-6 p-3 bg-slate-900 border border-slate-700 rounded-lg text-[11px] font-mono text-slate-300 shadow-xl whitespace-pre">
                {`School: ${data.school_cfg?.school_id ?? "unset"} (${data.school_cfg?.meal_type ?? "?"})\nSkylight: ${data.skylight_cfg?.email ?? "unset"}${data.skylight_cfg?.frame_id ? ` (frame ${data.skylight_cfg.frame_id})` : ""}`}
              </pre>
            </details>
            <Link
              to="/admin"
              className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium transition-colors"
            >
              Menu sync admin &rarr;
            </Link>
          </div>
        </footer>
      </main>
    </div>
  )
}
