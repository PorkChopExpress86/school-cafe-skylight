export interface CatalogControlsProps {
  searchQuery: string
  onSearchQueryChange: (searchQuery: string) => void
  isApplyingCasing: boolean
  onApplyCasing: () => void
}

export function CatalogControls({ searchQuery, onSearchQueryChange, isApplyingCasing, onApplyCasing }: CatalogControlsProps) {
  return (
    <div className="flex flex-col sm:flex-row items-center gap-2.5 w-full md:w-auto">
      <input
        type="text"
        value={searchQuery}
        onChange={(event) => onSearchQueryChange(event.target.value)}
        placeholder="Search items..."
        className="w-full sm:w-48 px-3 py-1.5 text-xs rounded-lg bg-slate-800 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-red-500 focus:ring-1 focus:ring-red-500"
      />
      <button
        type="button"
        onClick={onApplyCasing}
        disabled={isApplyingCasing}
        className="w-full sm:w-auto px-3.5 py-1.5 text-xs font-bold rounded-lg bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 text-white border border-blue-500/30 transition-all shadow-sm active:scale-95 disabled:opacity-50 whitespace-nowrap flex items-center justify-center gap-1.5"
      >
        {isApplyingCasing ? (
          <>
            <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            <span>Running agy AI Casing...</span>
          </>
        ) : (
          <>
            <span>🤖</span>
            <span>Auto-Case All Items (agy AI)</span>
          </>
        )}
      </button>
    </div>
  )
}
