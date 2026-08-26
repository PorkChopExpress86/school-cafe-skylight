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

function shiftDate(menuDate: string, amount: number): string {
  const [year, month, day] = menuDate.split("-").map(Number)
  const date = new Date(Date.UTC(year, month - 1, day + amount))
  return date.toISOString().slice(0, 10)
}

function shortDateLabel(menuDate: string): string {
  return new Date(`${menuDate}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

interface CalendarCell {
  menuDate: string
  isCurrentMonth: boolean
}

function calendarCells(month: string): CalendarCell[] {
  const dates = monthDates(month)
  const leadingDays = weekdayOffset(month)
  const leadingCells = Array.from({ length: leadingDays }, (_, index) => ({
    menuDate: shiftDate(dates[0], index - leadingDays),
    isCurrentMonth: false,
  }))
  const currentCells = dates.map((menuDate) => ({ menuDate, isCurrentMonth: true }))
  const trailingDays = (7 - ((leadingCells.length + currentCells.length) % 7)) % 7
  const trailingCells = Array.from({ length: trailingDays }, (_, index) => ({
    menuDate: shiftDate(dates.at(-1) ?? dates[0], index + 1),
    isCurrentMonth: false,
  }))

  return [...leadingCells, ...currentCells, ...trailingCells]
}

function kidShortLabels(kids: Kid[]): Record<number, string> {
  const firstNames = new Map(kids.map((kid) => [kid.id, kid.name.trim().split(/\s+/)[0] || kid.name]))

  return Object.fromEntries(kids.map((kid) => {
    const firstName = firstNames.get(kid.id) ?? kid.name
    const characters = Array.from(firstName)
    const firstCharacter = characters[0] ?? "?"

    for (let length = 1; length <= characters.length; length += 1) {
      const label = characters.slice(0, length).join("")
      const isUnique = kids.every((otherKid) => {
        if (otherKid.id === kid.id) return true
        const otherName = firstNames.get(otherKid.id) ?? otherKid.name
        return !otherName.toLocaleLowerCase().startsWith(label.toLocaleLowerCase())
      })
      if (isUnique) return [kid.id, label]
    }

    return [kid.id, `${firstCharacter}${kid.id}`]
  }))
}

interface KidMarkerProps {
  kid: Kid
  shortLabel: string
  state: SelectionPublicationState | undefined
}

function KidMarker({ kid, shortLabel, state }: KidMarkerProps) {
  const status = state ? STATUS_LABELS[state] : "No selection"
  const className = state
    ? `inline-flex h-6 min-w-6 items-center justify-center rounded-full border px-1 text-[10px] font-bold ${STATUS_CLASSES[state]}`
    : "inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-slate-700 px-1 text-[10px] font-bold text-slate-500"

  return (
    <span aria-label={`${kid.name}: ${status}`} className={className} role="img" style={state ? { backgroundColor: `${kid.color}33` } : undefined}>
      {shortLabel}
    </span>
  )
}

interface AdjacentMonthDayProps {
  menuDate: string
}

function AdjacentMonthDay({ menuDate }: AdjacentMonthDayProps) {
  return (
    <article aria-label={`${shortDateLabel(menuDate)} (adjacent month)`} className="min-h-24 rounded-lg border border-slate-900 bg-slate-950/20 p-2 text-slate-700 opacity-70">
      <time dateTime={menuDate} className="text-xs font-bold">{Number(menuDate.slice(-2))}</time>
      <span className="sr-only">Adjacent month</span>
    </article>
  )
}

interface CalendarDayProps {
  menuDate: string
  availability: SchoolMenuAvailability
  kids: Kid[]
  kidLabels: Record<number, string>
  selections: Record<number, { publication_state: SelectionPublicationState }>
  picked: number
  totalKids: number
  isToday: boolean
}

function CalendarDay({ menuDate, availability, kids, kidLabels, selections, picked, totalKids, isToday }: CalendarDayProps) {
  const className = `min-h-24 rounded-lg border p-2 transition-colors ${isToday ? "border-amber-400 bg-amber-950/30" : AVAILABILITY_CLASSES[availability]}`
  const content = (
    <>
      <div className="flex items-center justify-between gap-1">
        <time dateTime={menuDate} className="text-xs font-bold text-slate-300">{Number(menuDate.slice(-2))}</time>
        {totalKids > 0 && <span className="text-[10px] text-slate-500">{picked}/{totalKids} picked</span>}
      </div>
      <span className="mt-1 block text-[10px] font-semibold text-slate-500">{AVAILABILITY_LABELS[availability]}</span>
      <div className="mt-2 flex flex-wrap gap-1">
        {kids.map((kid) => <KidMarker key={kid.id} kid={kid} shortLabel={kidLabels[kid.id]} state={selections[kid.id]?.publication_state} />)}
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
  const { data, isLoading, error, refetch } = useMonth(requestedMonth)

  if (isLoading) {
    return <div className="min-h-screen bg-slate-950 p-6 text-slate-300">Loading lunch calendar...</div>
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-slate-950 p-6 text-red-200">
        <div role="alert" className="mx-auto max-w-xl rounded-xl border border-red-800/80 bg-red-950/80 p-4 shadow-lg">
          <p className="font-semibold text-red-100">Could not load the lunch calendar.</p>
          <p className="mt-1 text-sm">{error instanceof Error ? error.message : "Network error"}</p>
          <button onClick={() => void refetch()} className="mt-4 rounded-lg border border-red-500/70 bg-red-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-800">
            Try again
          </button>
        </div>
      </div>
    )
  }

  const cells = calendarCells(data.month)
  const totalKids = data.kids.length
  const kidLabels = kidShortLabels(data.kids)
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
          <div aria-describedby="calendar-scroll-help" aria-label="Monthly lunch calendar" className="mt-4 overflow-x-auto pb-1" data-testid="calendar-scroll-region" role="region" tabIndex={0}>
            <p id="calendar-scroll-help" className="sr-only">Scroll horizontally to view all seven calendar days on smaller screens.</p>
            <div className="min-w-[42rem]" data-testid="calendar-grid">
              <div className="grid grid-cols-7 gap-1 text-center text-xs font-bold uppercase tracking-wide text-slate-500">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((weekday) => <span key={weekday}>{weekday}</span>)}
              </div>
              <div className="mt-2 grid grid-cols-7 gap-1">
                {cells.map(({ menuDate, isCurrentMonth }) => {
                  if (!isCurrentMonth) return <AdjacentMonthDay key={menuDate} menuDate={menuDate} />

              const selections = data.selections[menuDate] ?? {}
              const picked = data.day_totals[menuDate] ?? 0
              return (
                <CalendarDay
                  key={menuDate}
                  menuDate={menuDate}
                  availability={data.availability[menuDate] ?? "menu_unavailable"}
                  kids={data.kids}
                  kidLabels={kidLabels}
                  selections={selections}
                  picked={picked}
                  totalKids={totalKids}
                  isToday={menuDate === data.today}
                />
              )
                })}
              </div>
            </div>
          </div>
        </section>

        {totalKids === 0 && (
          <p className="rounded-xl border border-amber-800/70 bg-amber-950/60 p-4 text-sm text-amber-100" role="status">
            No Kids have been added yet. Add a Kid before choosing lunches.
          </p>
        )}

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
