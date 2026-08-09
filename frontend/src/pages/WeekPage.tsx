import { useState } from "react"
import { Link } from "react-router-dom"
import DaySection from "../components/DaySection"
import HistoryPanel from "../components/HistoryPanel"
import { useSelect, useSendDay, useWeek } from "../hooks/useApi"
import type { SendResult } from "../types"

export default function WeekPage() {
  const [date, setDate] = useState<string | undefined>(undefined)
  const { data, isLoading, error } = useWeek(date)
  const selectMutation = useSelect()
  const sendMutation = useSendDay()
  const [sendResults, setSendResults] = useState<Record<string, SendResult>>({})

  if (isLoading) {
    return <div className="max-w-5xl mx-auto px-4 py-6 text-slate-500">Loading menu...</div>
  }

  if (error || !data) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-6">
        <div className="mb-4 p-3 rounded-md bg-amber-100 text-amber-800 border border-amber-300 text-sm">
          Could not load the menu. {error instanceof Error ? error.message : ""}
        </div>
      </div>
    )
  }

  const weekStart = data.week.length > 0 ? data.week[0].date : data.ref
  const weekStartLabel = new Date(`${weekStart}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  })

  const handleSelect = (kidId: number, menuDate: string, selection: string) => {
    selectMutation.mutate({ kid_id: kidId, menu_date: menuDate, selection })
  }

  const handleSend = (menuDate: string) => {
    sendMutation.mutate(menuDate, {
      onSuccess: (result) => {
        setSendResults((prev) => ({ ...prev, [menuDate]: result }))
      },
    })
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-slate-800">School Lunch - week of {weekStartLabel}</h1>
        <nav className="flex gap-3 text-sm">
          <button
            onClick={() => setDate(data.prev_week)}
            className="px-3 py-1.5 bg-white rounded-md border border-slate-300 hover:bg-slate-50"
          >
            &larr; Prev
          </button>
          <button
            onClick={() => setDate(undefined)}
            className="px-3 py-1.5 bg-white rounded-md border border-slate-300 hover:bg-slate-50"
          >
            This week
          </button>
          <button
            onClick={() => setDate(data.next_week)}
            className="px-3 py-1.5 bg-white rounded-md border border-slate-300 hover:bg-slate-50"
          >
            Next &rarr;
          </button>
        </nav>
      </header>

      {!data.school_cfg && (
        <div className="mb-4 p-3 rounded-md bg-amber-100 text-amber-800 border border-amber-300 text-sm">
          Set <code className="bg-amber-200 px-1 rounded">SCHOOL_ID</code> in{" "}
          <code className="bg-amber-200 px-1 rounded">.env</code> to fetch the weekly menu.
        </div>
      )}
      {data.menu_error && (
        <div className="mb-4 p-3 rounded-md bg-amber-100 text-amber-800 border border-amber-300 text-sm">
          Could not fetch menu: {data.menu_error}
        </div>
      )}

      <div className="space-y-4">
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
              result={sendResults[day.date] ?? null}
              sending={sendMutation.isPending}
              onSelect={handleSelect}
              onSend={handleSend}
            />
          )
        })}
      </div>

      <HistoryPanel history={data.history} />

      <footer className="mt-6 text-xs text-slate-400">
        <details>
          <summary className="cursor-pointer hover:text-slate-600">Config</summary>
          <pre className="mt-2 p-3 bg-white rounded border border-slate-200">
            {`School: ${data.school_cfg?.school_id ?? "unset"} (${data.school_cfg?.meal_type ?? "?"})\nSkylight: ${data.skylight_cfg?.email ?? "unset"}${data.skylight_cfg?.frame_id ? ` (frame ${data.skylight_cfg.frame_id})` : ""}`}
          </pre>
        </details>
        <Link to="/admin" className="inline-block mt-2 hover:text-slate-600">
          Menu sync admin &rarr;
        </Link>
      </footer>
    </div>
  )
}
