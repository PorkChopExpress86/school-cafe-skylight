import { BrowserRouter, Route, Routes } from "react-router-dom"
import { AdminPage } from "../features/menu-catalog"
import { WeekPage } from "../features/planner"

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WeekPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </BrowserRouter>
  )
}
