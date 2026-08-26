import { BrowserRouter, Route, Routes } from "react-router-dom"
import { AdminPage } from "../features/menu-catalog"
import { CalendarPage, WeekPage } from "../features/planner"

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<WeekPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </BrowserRouter>
  )
}
