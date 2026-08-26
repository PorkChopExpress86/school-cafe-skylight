// @vitest-environment jsdom

import type { PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { select, sendDay, sendWeek } from "./api"
import type { SendResult } from "./types"
import { usePlannerInteraction } from "./usePlannerInteraction"

vi.mock("./api", () => ({
  select: vi.fn(),
  sendDay: vi.fn(),
  sendWeek: vi.fn(),
}))

const MENU_DATE = "2026-08-24"
const DAY_RESULT: SendResult = {
  ok: true,
  message: "Sent 1 to Skylight.",
  sent: 1,
  deleted: 0,
  skipped: 0,
  errors: [],
  results: [],
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderPlannerInteraction() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Number.POSITIVE_INFINITY },
      mutations: { retry: false, gcTime: Number.POSITIVE_INFINITY },
    },
  })
  const invalidate = vi.spyOn(queryClient, "invalidateQueries")
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { ...renderHook(() => usePlannerInteraction(), { wrapper }), invalidate }
}

describe("Planner Interaction State", () => {
  it("refreshes Planner Readback after a Selection Change", async () => {
    vi.mocked(select).mockResolvedValue({
      kid_id: 1,
      menu_date: MENU_DATE,
      selection: "Cheese Pizza",
      sent_at: null,
      day_totals: { [MENU_DATE]: 1 },
      day_sent: { [MENU_DATE]: 0 },
      history: [],
    })
    const { result, invalidate } = renderPlannerInteraction()

    act(() => result.current.forDate(MENU_DATE).onSelectionChange(1, MENU_DATE, "Cheese Pizza"))

    await waitFor(() => expect(select).toHaveBeenCalledWith(1, MENU_DATE, "Cheese Pizza"))
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["week"] }))
  })

  it("retains a day Publication Outcome and refreshes Planner Readback", async () => {
    vi.mocked(sendDay).mockResolvedValue(DAY_RESULT)
    const { result, invalidate } = renderPlannerInteraction()

    act(() => result.current.forDate(MENU_DATE).onPublication(MENU_DATE))

    await waitFor(() => expect(result.current.forDate(MENU_DATE).result).toEqual(DAY_RESULT))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["week"] })
  })

  it("retains a week Publication Outcome behind the week interaction", async () => {
    vi.mocked(sendWeek).mockResolvedValue(DAY_RESULT)
    const { result, invalidate } = renderPlannerInteraction()

    act(() => result.current.week.onPublication(MENU_DATE))

    await waitFor(() => expect(result.current.week.result).toEqual(DAY_RESULT))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["week"] })
  })
})
