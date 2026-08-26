// @vitest-environment jsdom

import type { PropsWithChildren } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import AdminPage from "./AdminPage"

const ADMIN_RESPONSE = {
  items: [
    { description: "CHEESE PIZZA", category: "Entree", display_description: "Cheese Pizza" },
    { description: "MILK", category: "Beverage", display_description: "Milk" },
  ],
  attempts: [
    {
      attempted_at: "2026-08-24T03:00:00",
      succeeded: false,
      weeks_fetched: 0,
      items_stored: 0,
      weeks_covered: "",
      error: "School menu unavailable",
    },
  ],
  last_success: {
    attempted_at: "2026-08-17T03:00:00",
    succeeded: true,
    weeks_fetched: 2,
    items_stored: 12,
    weeks_covered: "2026-08-17,2026-08-24",
    error: null,
  },
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown, status = 200, statusText = "OK"): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { "Content-Type": "application/json" },
  })
}

function renderAdminPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Number.POSITIVE_INFINITY },
      mutations: { retry: false, gcTime: Number.POSITIVE_INFINITY },
    },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )

  return render(<AdminPage />, { wrapper })
}

describe("Menu Catalog administration", () => {
  it("shows the loading state until administration data is available", async () => {
    let resolveResponse: (response: Response) => void
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveResponse = resolve
          }),
      ),
    )

    renderAdminPage()

    expect(screen.getByText("Loading Menu Sync Admin...")).toBeTruthy()
    resolveResponse!(jsonResponse(ADMIN_RESPONSE))
    expect(await screen.findByRole("heading", { name: "Menu Sync Admin" })).toBeTruthy()
  })

  it("supports item search, permanent overrides, refresh actions, and refresh history", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const path = typeof input === "string" ? input : input.toString()
      if (path === "/api/admin" && !init?.method) return jsonResponse(ADMIN_RESPONSE)
      if (path === "/api/admin/override") return jsonResponse({ ok: true })
      if (path === "/api/admin/sync") return jsonResponse({ ok: true, message: "Menu refreshed." })
      if (path === "/api/admin/llm-case-all") return jsonResponse({ ok: true, count: 2, updated: 2, message: "Items recased." })
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal("fetch", fetchMock)

    renderAdminPage()

    expect(await screen.findByRole("heading", { name: "Menu Sync Admin" })).toBeTruthy()
    expect(screen.getByText("School menu unavailable")).toBeTruthy()
    expect(screen.getByText("2 Unique Items")).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText("Search items..."), { target: { value: "pizza" } })
    expect(screen.getByText("CHEESE PIZZA")).toBeTruthy()
    expect(screen.queryByText("MILK")).toBeNull()

    fireEvent.change(screen.getByDisplayValue("Cheese Pizza"), { target: { value: "Perfect Pizza" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/override",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ original: "CHEESE PIZZA", replacement: "Perfect Pizza" }) }),
    ))

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }))
    expect(await screen.findByText("Menu refreshed.")).toBeTruthy()

    fireEvent.click(screen.getByRole("button", { name: /Auto-Case All Items/ }))
    expect(await screen.findByText("Items recased.")).toBeTruthy()
  })

  it("shows the administrative loading failure at the page seam", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Unavailable" }, 503, "Service Unavailable")))

    renderAdminPage()

    expect(await screen.findByText("Could not load admin data.")).toBeTruthy()
    expect(screen.getByText(/503 Service Unavailable/)).toBeTruthy()
  })
})
