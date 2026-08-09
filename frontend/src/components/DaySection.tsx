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
    year: "numeric",
  })

  return (
    <section className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-slate-50 border-b border-slate-200">
        <h2 className="font-semibold text-slate-700">
          {day.weekday}
          <span className="text-slate-400 font-normal ml-2">{dateLabel}</span>
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
        <div className="px-5 py-4 text-slate-400 italic text-sm">No entrees posted.</div>
      ) : (
        <div className="p-5">
          <div
            className="grid gap-x-3 items-center pb-2 mb-1 border-b border-slate-100 text-xs font-semibold text-slate-400 uppercase tracking-wide"
            style={gridCols}
          >
            <div>Entree</div>
            {kids.map((kid) => (
              <div key={kid.id} className="text-center min-w-20 whitespace-nowrap" style={{ color: kid.color }}>
                {kid.name}
              </div>
            ))}
          </div>

          {day.entrees.map((item) => (
            <div key={item} className="grid gap-x-3 items-center py-1.5 hover:bg-slate-50 rounded" style={gridCols}>
              <div className="text-sm text-slate-700">{item}</div>
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

          <div className="grid gap-x-3 items-center py-1.5 mt-2 pt-2 border-t border-slate-200" style={gridCols}>
            <div className="text-sm text-emerald-700 font-medium">Make at home</div>
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
