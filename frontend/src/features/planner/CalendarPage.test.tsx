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
  availability: { "2026-08-12": "available", "2026-08-13": "menu_unavailable", "2026-08-15": "non_school" },
  menu_catalog_freshness: "2026-08-10T03:00:00",
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

function renderWeekPage(initialEntry = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
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

  it("shows local menu availability and opens only an eligible date", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(MONTH_RESPONSE), { headers: { "Content-Type": "application/json" } })),
    )

    renderCalendarPage()

    expect(await screen.findByText("Menu catalog last refreshed: Aug 10, 2026")).toBeTruthy()
    expect(screen.getByRole("link", { name: "Open week of 2026-08-12" }).getAttribute("href")).toBe("/?date=2026-08-12")
    expect(screen.getAllByText("Menu unavailable").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Non-school").length).toBeGreaterThan(0)
    expect(screen.queryByRole("link", { name: "Open week of 2026-08-13" })).toBeNull()
  })

  it("explains when the month has no known menu availability", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ...MONTH_RESPONSE, availability: {}, menu_catalog_freshness: null }), {
        headers: { "Content-Type": "application/json" },
      })),
    )

    renderCalendarPage()

    expect(await screen.findByText(
      "Menu catalog has not refreshed successfully. No menu currently available for August 2026.",
    )).toBeTruthy()
  })

  it("keeps a scrollable seven-column grid and mutes adjacent-month dates", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(MONTH_RESPONSE), { headers: { "Content-Type": "application/json" } })),
    )

    renderCalendarPage()

    expect((await screen.findByTestId("calendar-scroll-region")).className).toContain("overflow-x-auto")
    expect(screen.getByTestId("calendar-grid").className).toContain("min-w-[42rem]")
    expect(screen.getByLabelText("Jul 26, 2026 (adjacent month)")).toBeTruthy()
    expect(screen.queryByRole("link", { name: "Open week of 2026-07-26" })).toBeNull()
  })

  it("uses unique visible identities for Kids with matching initials and exposes full status text", async () => {
    const matchingInitialsResponse = {
      ...MONTH_RESPONSE,
      kids: [
        { id: 1, name: "Parker", color: "#3B82F6", prefix: "P-" },
        { id: 2, name: "Peyton", color: "#EC4899", prefix: "P-" },
      ],
      selections: {
        "2026-08-12": {
          1: { selection: "Cheese Pizza", sent_at: null, sent_sitting_id: null, publication_state: "pending" },
          2: { selection: "Chicken Tenders", sent_at: null, sent_sitting_id: null, publication_state: "pending" },
        },
      },
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(matchingInitialsResponse), { headers: { "Content-Type": "application/json" } })),
    )

    renderCalendarPage()

    expect((await screen.findByRole("img", { name: "Parker: Pending" })).textContent).toBe("Pa")
    expect(screen.getByRole("img", { name: "Peyton: Pending" }).textContent).toBe("Pe")
  })

  it("explains the no-Kid state without claiming selections can be made", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ...MONTH_RESPONSE, kids: [] }), { headers: { "Content-Type": "application/json" } })),
    )

    renderCalendarPage()

    expect(await screen.findByText("No Kids have been added yet. Add a Kid before choosing lunches.")).toBeTruthy()
    expect(screen.queryByText("0/0 picked")).toBeNull()
  })

  it("replaces calendar data with a retryable error when loading fails", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("Offline"))
      .mockResolvedValueOnce(new Response(JSON.stringify(MONTH_RESPONSE), { headers: { "Content-Type": "application/json" } }))
    vi.stubGlobal("fetch", fetchMock)

    renderCalendarPage()

    expect((await screen.findByRole("alert")).textContent).toContain("Could not load the lunch calendar")
    expect(screen.queryByText("August 2026")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(await screen.findByText("August 2026")).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it("loads the selected available date in the week planner", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      week: [], kids: [], selections: {}, day_totals: {}, day_sent: {}, history: [],
      ref: "2026-08-12", prev_week: "2026-08-05", next_week: "2026-08-19", today: "2026-08-12",
      school_cfg: null, skylight_cfg: null, menu_error: null,
    }), { headers: { "Content-Type": "application/json" } }))
    vi.stubGlobal("fetch", fetchMock)

    renderWeekPage("/?date=2026-08-12")

    await screen.findByRole("link", { name: "Calendar" })
    expect(fetchMock).toHaveBeenCalledWith("/api/week?date=2026-08-12", expect.any(Object))
  })
})
