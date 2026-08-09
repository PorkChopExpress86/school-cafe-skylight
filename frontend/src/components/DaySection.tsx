import { MAKE_AT_HOME, type DayMenu, type Kid, type SelectionState } from "../types"
import Cell from "./Cell"
import SendButton from "./SendButton"
import type { SendResult } from "../types"

interface DaySectionProps {
  day: DayMenu
  kids: Kid[]
  selections: Record<number, SelectionState>
  total: number
  sentCount: number
  result: SendResult | null
  sending: boolean
  onSelect: (kidId: number, menuDate: string, selection: string) => void
  onSend: (menuDate: string) => void
}

export default function DaySection({
  day,
  kids,
  selections,
  total,
  sentCount,
  result,
  sending,
  onSelect,
  onSend,
}: DaySectionProps) {
  const gridCols = { gridTemplateColumns: `1fr repeat(${kids.length}, auto)` }

  const dateObj = new Date(`${day.date}T00:00:00`)
  const dateLabel = dateObj.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  })

  return (
    <section className="bg-slate-900 rounded-xl shadow-lg border border-slate-800 overflow-hidden transition-all hover:border-slate-700">
      <div className="flex flex-wrap items-center justify-between px-5 py-3.5 bg-slate-850 border-b border-slate-800 gap-2">
        <h2 className="font-bold text-white tracking-wide text-base flex items-center gap-2">
          <span className="text-red-500 font-extrabold">{day.weekday}</span>
          <span className="text-slate-400 font-medium text-xs bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
            {dateLabel}
          </span>
        </h2>
        <SendButton
          menuDate={day.date}
          total={total}
          sentCount={sentCount}
          result={result}
          onSend={onSend}
          sending={sending}
        />
      </div>

      {day.entrees.length === 0 ? (
        <div className="px-5 py-5 text-slate-500 italic text-sm text-center">No entrees posted for this date.</div>
      ) : (
        <div className="p-5">
          <div
            className="grid gap-x-4 items-center pb-2.5 mb-2 border-b border-slate-800 text-xs font-bold text-slate-400 uppercase tracking-wider"
            style={gridCols}
          >
            <div>Entree</div>
            {kids.map((kid) => (
              <div
                key={kid.id}
                className="text-center min-w-20 whitespace-nowrap px-2 py-0.5 rounded font-extrabold text-xs"
                style={{ color: kid.color }}
              >
                {kid.name}
              </div>
            ))}
          </div>

          <div className="space-y-1">
            {day.entrees.map((item) => (
              <div
                key={item}
                className="grid gap-x-4 items-center py-2 px-2 hover:bg-slate-800/60 rounded-lg transition-colors"
                style={gridCols}
              >
                <div className="text-sm font-medium text-slate-200">{item}</div>
                {kids.map((kid) => {
                  const current = selections[kid.id]
                  const selected = current?.selection === item
                  const isSent = selected && Boolean(current?.sent_at)
                  return (
                    <Cell
                      key={kid.id}
                      kid={kid}
                      menuDate={day.date}
                      item={item}
                      selected={selected}
                      isSent={isSent}
                      onSelect={onSelect}
                    />
                  )
                })}
              </div>
            ))}
          </div>

          <div
            className="grid gap-x-4 items-center py-2 px-2 mt-3 pt-3 border-t border-slate-800/80 bg-emerald-950/20 rounded-lg"
            style={gridCols}
          >
            <div className="text-sm text-emerald-400 font-semibold flex items-center gap-1.5">
              <span>🏠</span>
              <span>Make at home</span>
            </div>
            {kids.map((kid) => {
              const current = selections[kid.id]
              const selected = current?.selection === MAKE_AT_HOME
              const isSent = selected && Boolean(current?.sent_at)
              return (
                <Cell
                  key={kid.id}
                  kid={kid}
                  menuDate={day.date}
                  item={MAKE_AT_HOME}
                  selected={selected}
                  isSent={isSent}
                  onSelect={onSelect}
                />
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
