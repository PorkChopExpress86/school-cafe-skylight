// @vitest-environment jsdom

import type { PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import CalendarPage from "./CalendarPage"

const MONTH_RESPONSE = {
  month: "2026-08",
  today: "2026-08-12",
  kids: [
    { id: 1, name: "Parker", color: "#3B82F6", prefix: "P-" },
    { id: 2, name: "Kylee", color: "#EC4899", prefix: "K-" },
  ],
  selections: {
    "2026-08-12": {
      1: { selection: "Cheese Pizza", sent_at: "2026-08-12T12:00:00", sent_sitting_id: "sitting-1", publication_state: "published" },
      2: { selection: "__MAKE_AT_HOME__", sent_at: "2026-08-12T12:00:00", sent_sitting_id: null, publication_state: "make_at_home" },
    },
  },
  day_totals: { "2026-08-12": 2 },
  day_sent: { "2026-08-12": 1 },
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderCalendarPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )

  return render(<CalendarPage />, { wrapper })
}

describe("Month Planner Readback calendar", () => {
  it("shows the current month, compact selection summaries, and state legend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(MONTH_RESPONSE), { headers: { "Content-Type": "application/json" } })),
    )

    renderCalendarPage()

    expect(await screen.findByRole("heading", { name: "Lunch calendar" })).toBeTruthy()
    expect(screen.getByText("August 2026")).toBeTruthy()
    expect(screen.getByText("2/2 picked")).toBeTruthy()
    expect(screen.getByLabelText("Parker: Published")).toBeTruthy()
    expect(screen.getByLabelText("Kylee: Make at Home")).toBeTruthy()
    expect(screen.getByText("Pending")).toBeTruthy()
    expect(screen.getByText("Published")).toBeTruthy()
    expect(screen.getByText("Make at Home")).toBeTruthy()
  })
})
