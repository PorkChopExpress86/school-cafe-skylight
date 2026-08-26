import { Link, useSearchParams } from "react-router-dom"
import { type Kid, type SchoolMenuAvailability, type SelectionPublicationState } from "./types"
import { useMonth } from "./usePlannerApi"

const STATUS_LABELS: Record<SelectionPublicationState, string> = {
  pending: "Pending",
  published: "Published",
  make_at_home: "Make at Home",
}

const STATUS_CLASSES: Record<SelectionPublicationState, string> = {
  pending: "border-amber-400 text-amber-200",
  published: "border-sky-400 text-sky-200",
  make_at_home: "border-emerald-400 text-emerald-200",
}

const AVAILABILITY_LABELS: Record<SchoolMenuAvailability, string> = {
  available: "Menu available",
  menu_unavailable: "Menu unavailable",
  non_school: "Non-school",
}

const AVAILABILITY_CLASSES: Record<SchoolMenuAvailability, string> = {
  available: "border-blue-500/70 bg-blue-950/20 hover:border-blue-400",
  menu_unavailable: "border-slate-800 bg-slate-950/50",
  non_school: "border-slate-800 bg-slate-950/30 opacity-60",
}

function monthDates(month: string): string[] {
  const [year, monthNumber] = month.split("-").map(Number)
  const days = new Date(year, monthNumber, 0).getDate()
  return Array.from({ length: days }, (_, index) => `${month}-${String(index + 1).padStart(2, "0")}`)
}

function monthLabel(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number)
  return new Date(year, monthNumber - 1, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" })
}

function weekdayOffset(month: string): number {
  const [year, monthNumber] = month.split("-").map(Number)
  return new Date(year, monthNumber - 1, 1).getDay()
}

interface KidMarkerProps {
  kid: Kid
  state: SelectionPublicationState | undefined
}

function KidMarker({ kid, state }: KidMarkerProps) {
  if (!state) {
    return (
      <span aria-label={`${kid.name}: No selection`} className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-700 text-[10px] font-bold text-slate-500">
        {kid.name[0]}
      </span>
    )
  }

  return (
    <span
      aria-label={`${kid.name}: ${STATUS_LABELS[state]}`}
      className={`inline-flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-bold ${STATUS_CLASSES[state]}`}
      style={{ backgroundColor: `${kid.color}33` }}
    >
      {kid.name[0]}
    </span>
  )
}

interface CalendarDayProps {
  menuDate: string
  availability: SchoolMenuAvailability
  kids: Kid[]
  selections: Record<number, { publication_state: SelectionPublicationState }>
  picked: number
  totalKids: number
  isToday: boolean
}

function CalendarDay({ menuDate, availability, kids, selections, picked, totalKids, isToday }: CalendarDayProps) {
  const className = `min-h-24 rounded-lg border p-2 transition-colors ${isToday ? "border-amber-400 bg-amber-950/30" : AVAILABILITY_CLASSES[availability]}`
  const content = (
    <>
      <div className="flex items-center justify-between gap-1">
        <time dateTime={menuDate} className="text-xs font-bold text-slate-300">{Number(menuDate.slice(-2))}</time>
        <span className="text-[10px] text-slate-500">{picked}/{totalKids} picked</span>
      </div>
      <span className="mt-1 block text-[10px] font-semibold text-slate-500">{AVAILABILITY_LABELS[availability]}</span>
      <div className="mt-2 flex flex-wrap gap-1">
        {kids.map((kid) => <KidMarker key={kid.id} kid={kid} state={selections[kid.id]?.publication_state} />)}
      </div>
    </>
  )

  if (availability === "available") {
    return <Link to={`/?date=${menuDate}`} aria-label={`Open week of ${menuDate}`} className={`block ${className}`}>{content}</Link>
  }

  return <article className={className}>{content}</article>
}

function freshnessLabel(value: string): string {
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

export default function CalendarPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedMonth = searchParams.get("month") ?? undefined
  const { data, isLoading, error } = useMonth(requestedMonth)

  if (isLoading) {
    return <div className="min-h-screen bg-slate-950 p-6 text-slate-300">Loading lunch calendar...</div>
  }

  if (error || !data) {
    return <div className="min-h-screen bg-slate-950 p-6 text-red-200">Could not load the lunch calendar.</div>
  }

  const dates = monthDates(data.month)
  const totalKids = data.kids.length
  const hasAvailableMenu = Object.values(data.availability).some((availability) => availability === "available")
  const handleMonthChange = (month: string) => setSearchParams({ month })

  return (
    <div className="min-h-screen bg-slate-950 pb-12 text-slate-100">
      <div className="h-1.5 w-full bg-gradient-to-r from-blue-700 via-red-600 to-amber-400" />
      <header className="border-b border-slate-800 bg-slate-900/90 shadow-md backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-red-500">School Lunch Planner</p>
            <h1 className="text-xl font-extrabold text-white">Lunch calendar</h1>
          </div>
          <Link to="/" className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700">
            Week planner
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 px-4 pt-6">
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-white">{monthLabel(data.month)}</h2>
            <nav aria-label="Calendar month navigation" className="flex items-center gap-2">
              <button onClick={() => handleMonthChange(data.prev_month)} className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700">
                Prev month
              </button>
              <button onClick={() => handleMonthChange(data.current_month)} className="rounded-lg border border-blue-500 bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500">
                Today
              </button>
              <button onClick={() => handleMonthChange(data.next_month)} className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700">
                Next month
              </button>
            </nav>
          </div>
          <div className="mt-4 grid grid-cols-7 gap-1 text-center text-xs font-bold uppercase tracking-wide text-slate-500">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((weekday) => <span key={weekday}>{weekday}</span>)}
          </div>
          <div className="mt-2 grid grid-cols-7 gap-1">
            {Array.from({ length: weekdayOffset(data.month) }, (_, index) => <div key={`blank-${index}`} />)}
            {dates.map((menuDate) => {
              const selections = data.selections[menuDate] ?? {}
              const picked = data.day_totals[menuDate] ?? 0
              return (
                <CalendarDay
                  key={menuDate}
                  menuDate={menuDate}
                  availability={data.availability[menuDate] ?? "menu_unavailable"}
                  kids={data.kids}
                  selections={selections}
                  picked={picked}
                  totalKids={totalKids}
                  isToday={menuDate === data.today}
                />
              )
            })}
          </div>
        </section>

        <p className="text-sm text-slate-400">
          {data.menu_catalog_freshness
            ? `Menu catalog last refreshed: ${freshnessLabel(data.menu_catalog_freshness)}`
            : "Menu catalog has not refreshed successfully."}
          {!hasAvailableMenu && ` No menu currently available for ${monthLabel(data.month)}.`}
        </p>

        <section aria-label="Selection status legend" className="flex flex-wrap gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4 text-xs text-slate-300">
          {(Object.keys(STATUS_LABELS) as SelectionPublicationState[]).map((state) => (
            <span key={state} className={`rounded-full border px-2 py-1 font-semibold ${STATUS_CLASSES[state]}`}>{STATUS_LABELS[state]}</span>
          ))}
        </section>
      </main>
    </div>
  )
}
