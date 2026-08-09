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
    <div className="flex items-center gap-2.5">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSend(menuDate)}
        className={`px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all shadow-sm active:scale-95 flex items-center gap-1.5 ${
          disabled
            ? "bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed opacity-60"
            : "bg-gradient-to-r from-red-600 to-red-700 hover:from-red-500 hover:to-red-600 text-white border border-red-500/40 shadow-red-950/40"
        }`}
      >
        {sending ? (
          <>
            <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            <span>Sending...</span>
          </>
        ) : (
          <>
            <span>📅</span>
            <span>Send to Skylight</span>
          </>
        )}
      </button>
      <div className="text-xs font-medium">
        {result ? (
          <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${result.ok ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60" : "bg-amber-950/80 text-amber-300 border border-amber-800/60"}`}>
            {result.message}
          </span>
        ) : total ? (
          <span className="text-slate-400 font-mono text-[11px] bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700/80">
            {sentCount}/{total} sent
          </span>
        ) : null}
      </div>
    </div>
  )
}
