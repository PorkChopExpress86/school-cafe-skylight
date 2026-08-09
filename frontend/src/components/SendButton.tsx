import type { SendResult } from "../types"

interface SendButtonProps {
  menuDate: string
  total: number
  sentCount: number
  result: SendResult | null
  onSend: (menuDate: string) => void
  sending: boolean
}

export default function SendButton({ menuDate, total, sentCount, result, onSend, sending }: SendButtonProps) {
  const disabled = total === 0 || sending

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSend(menuDate)}
        className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
          disabled
            ? "bg-slate-200 text-slate-400 cursor-not-allowed"
            : "bg-slate-800 text-white hover:bg-slate-700"
        }`}
      >
        {sending ? "Sending..." : "Send to Skylight"}
      </button>
      <div className="text-xs text-slate-400">
        {result ? (
          <span className={result.ok ? "text-emerald-600" : "text-amber-600"}>
            {result.message}
          </span>
        ) : total ? (
          `${sentCount}/${total} sent`
        ) : null}
      </div>
    </div>
  )
}
