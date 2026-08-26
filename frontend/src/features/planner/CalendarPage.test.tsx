// @vitest-environment jsdom

import type { PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import CalendarPage from "./CalendarPage"
import WeekPage from "./WeekPage"

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
  prev_month: "2026-07",
  next_month: "2026-09",
  current_month: "2026-08",
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function LocationDisplay() {
  const location = useLocation()
  return <output aria-label="Current location">{location.search}</output>
}

function renderCalendarPage(initialEntry = "/calendar") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
    </QueryClientProvider>
  )

  return render(
    <>
      <CalendarPage />
      <LocationDisplay />
    </>,
    { wrapper },
  )
}

function renderWeekPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )

  return render(<WeekPage />, { wrapper })
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

  it("moves between addressable months and returns to today", async () => {
    const septemberResponse = { ...MONTH_RESPONSE, month: "2026-09", prev_month: "2026-08", next_month: "2026-10" }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const path = typeof input === "string" ? input : input.toString()
        const response = path === "/api/month?month=2026-09" ? septemberResponse : MONTH_RESPONSE
        return new Response(JSON.stringify(response), { headers: { "Content-Type": "application/json" } })
      }),
    )

    renderCalendarPage("/calendar?month=2026-08")

    await screen.findByText("August 2026")
    fireEvent.click(screen.getByRole("button", { name: "Next month" }))
    expect(await screen.findByText("September 2026")).toBeTruthy()
    expect(screen.getByLabelText("Current location").textContent).toBe("?month=2026-09")

    fireEvent.click(screen.getByRole("button", { name: "Today" }))
    expect(await screen.findByText("August 2026")).toBeTruthy()
    expect(screen.getByLabelText("Current location").textContent).toBe("?month=2026-08")
  })

  it("opens the calendar for the displayed week’s month", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({
        week: [], kids: [], selections: {}, day_totals: {}, day_sent: {}, history: [],
        ref: "2026-09-16", prev_week: "2026-09-09", next_week: "2026-09-23", today: "2026-08-12",
        school_cfg: null, skylight_cfg: null, menu_error: null,
      }), { headers: { "Content-Type": "application/json" } })),
    )

    renderWeekPage()

    const calendar = await screen.findByRole("link", { name: "Calendar" })
    expect(calendar.getAttribute("href")).toBe("/calendar?month=2026-09")
  })
})
