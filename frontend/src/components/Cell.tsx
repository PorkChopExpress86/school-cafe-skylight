import { MAKE_AT_HOME, type Kid, type SelectionPublicationState } from "../types"

interface CellProps {
  kid: Kid
  menuDate: string
  item: string
  selected: boolean
  isLocked: boolean
  publicationState: SelectionPublicationState
  onSelect: (kidId: number, menuDate: string, selection: string) => void
}

export default function Cell({ kid, menuDate, item, selected, isLocked, publicationState, onSelect }: CellProps) {
  const isMakeHome = item === MAKE_AT_HOME
  const isSent = isLocked

  let className =
    "inline-flex items-center justify-center w-8 h-8 rounded-full border-2 text-xs font-bold transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500 active:scale-95 shadow-sm "
  if (isSent) {
    className += "border-slate-600 text-slate-400 bg-slate-800 cursor-default opacity-80"
  } else if (selected) {
    className += isMakeHome
      ? "border-emerald-500 text-white bg-emerald-600 shadow-emerald-900/50 shadow-md"
      : "text-white shadow-md"
  } else {
    className += "border-slate-700 text-transparent hover:border-slate-500 hover:text-slate-500 bg-slate-900/40"
  }

  const style =
    selected && !isMakeHome && !isSent
      ? { borderColor: kid.color, backgroundColor: kid.color, boxShadow: `0 4px 12px ${kid.color}40` }
      : undefined

  const label = isMakeHome
    ? `${kid.name} will make at home`
    : `${kid.name} will eat ${item}`
  const ariaLabel = isLocked
    ? `${label} (${publicationState === "published" ? "published to Skylight" : "included as Make at Home"})`
    : label

  return (
    <div className="text-center min-w-20 flex justify-center">
      <button
        type="button"
        className={className}
        style={style}
        aria-label={ariaLabel}
        disabled={isLocked}
        onClick={() => onSelect(kid.id, menuDate, item)}
      >
        {isSent ? "✓✓" : selected ? "✓" : "·"}
      </button>
    </div>
  )
}
