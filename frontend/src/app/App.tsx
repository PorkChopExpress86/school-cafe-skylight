import { AppRouter } from "./AppRouter"

export default function App() {
  return (
    <div className="bg-slate-900 text-slate-100 min-h-screen font-sans antialiased selection:bg-red-500 selection:text-white">
      <AppRouter />
    </div>
  )
}
