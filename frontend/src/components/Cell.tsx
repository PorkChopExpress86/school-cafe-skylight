import { MAKE_AT_HOME, type Kid } from "../types"

interface CellProps {
  kid: Kid
  menuDate: string
  item: string
  selected: boolean
  isSent: boolean
  onSelect: (kidId: number, menuDate: string, selection: string) => void
}

export default function Cell({ kid, menuDate, item, selected, isSent, onSelect }: CellProps) {
  const isMakeHome = item === MAKE_AT_HOME

  let className =
    "inline-flex items-center justify-center w-7 h-7 rounded-full border-2 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-slate-500 "
  if (isSent) {
    className += "border-slate-400 text-slate-400 bg-transparent cursor-default"
  } else if (selected) {
    className += isMakeHome
      ? "border-emerald-500 text-white bg-emerald-500"
      : "text-white"
  } else {
    className += "border-slate-200 text-transparent hover:border-slate-400"
  }

  const style =
    selected && !isMakeHome && !isSent
      ? { borderColor: kid.color, backgroundColor: kid.color }
      : undefined

  const label = isMakeHome
    ? `${kid.name} will make at home`
    : `${kid.name} will eat ${item}`
  const ariaLabel = isSent ? `${label} (sent to Skylight)` : label

  return (
    <div className="text-center min-w-20">
      <button
        type="button"
        className={className}
        style={style}
        aria-label={ariaLabel}
        disabled={isSent}
        onClick={() => onSelect(kid.id, menuDate, item)}
      >
        {isSent ? "\u2713\u2713" : selected ? "\u2713" : "\u00b7"}
      </button>
    </div>
  )
}
