import { useState } from "react"
import type { AdminItem } from "../types"

export interface CatalogItemsProps {
  items: AdminItem[]
  totalItemCount: number
  searchQuery: string
  isSaving: boolean
  onSave: (original: string, replacement: string) => void
  onClear: (original: string) => void
}

export function CatalogItems({ items, totalItemCount, searchQuery, isSaving, onSave, onClear }: CatalogItemsProps) {
  const [edits, setEdits] = useState<Record<string, string>>({})

  if (totalItemCount === 0) {
    return <div className="px-5 py-8 text-sm text-slate-500 italic text-center">No menu items cached yet. Click "Sync now" above to fetch the school menu.</div>
  }

  if (items.length === 0) {
    return <div className="px-5 py-8 text-sm text-slate-500 italic text-center">No menu items match "{searchQuery}".</div>
  }

  const handleSave = (original: string) => {
    const replacement = (edits[original] ?? "").trim()
    onSave(original, replacement)
  }

  const handleClear = (original: string) => {
    setEdits((previousEdits) => ({ ...previousEdits, [original]: "" }))
    onClear(original)
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[11px] text-slate-400 uppercase tracking-wider border-b border-slate-800 bg-slate-900/80">
            <th className="text-left font-semibold py-3 px-5">Active Display Name</th>
            <th className="text-left font-semibold py-3 px-5">Original Source Description</th>
            <th className="text-left font-semibold py-3 px-5">Permanent Override Edit</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {items.map((item) => {
            const isOverridden = item.display_description !== item.description
            const currentInput = edits[item.description] ?? item.display_description

            return (
              <tr key={item.description} className="hover:bg-slate-800/40 transition-colors">
                <td className="py-3 px-5 font-semibold text-slate-100">
                  <div className="flex items-center gap-2">
                    <span>{item.display_description}</span>
                    {isOverridden ? (
                      <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider bg-amber-950/80 text-amber-300 border border-amber-800/60 shadow-sm">
                        Overridden
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider bg-slate-800 text-slate-400 border border-slate-700">
                        Original
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3 px-5 text-slate-400 font-mono text-xs">{item.description}</td>
                <td className="py-3 px-5">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={currentInput}
                      onChange={(event) => setEdits((previousEdits) => ({ ...previousEdits, [item.description]: event.target.value }))}
                      className="px-3 py-1.5 text-xs rounded-lg bg-slate-800 border border-slate-700 text-slate-100 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500 w-56 font-medium"
                      placeholder="Display name"
                    />
                    <button
                      onClick={() => handleSave(item.description)}
                      disabled={isSaving}
                      className="px-3 py-1.5 text-xs font-bold rounded-lg bg-blue-600 hover:bg-blue-500 text-white border border-blue-500/30 transition-all active:scale-95 disabled:opacity-50 shadow-sm"
                    >
                      Save
                    </button>
                    {isOverridden && (
                      <button
                        onClick={() => handleClear(item.description)}
                        disabled={isSaving}
                        className="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
                        title="Reset to original description"
                      >
                        Reset
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
