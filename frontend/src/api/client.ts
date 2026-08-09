// Typed API client for the FastAPI backend.
// In dev, Vite proxies /api to http://127.0.0.1:8000.
// In production, the SPA is served by FastAPI itself (same origin).

import type {
  AdminResponse,
  SelectResponse,
  SendResult,
  SyncResponse,
  WeekResponse,
} from "../types"

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

export function getWeek(date?: string): Promise<WeekResponse> {
  const q = date ? `?date=${encodeURIComponent(date)}` : ""
  return request<WeekResponse>(`/api/week${q}`)
}

export function select(
  kid_id: number,
  menu_date: string,
  selection: string,
): Promise<SelectResponse> {
  return request<SelectResponse>("/api/select", {
    method: "POST",
    body: JSON.stringify({ kid_id, menu_date, selection }),
  })
}

export function sendDay(menu_date: string): Promise<SendResult> {
  return request<SendResult>("/api/send-day", {
    method: "POST",
    body: JSON.stringify({ menu_date }),
  })
}

export function getAdmin(): Promise<AdminResponse> {
  return request<AdminResponse>("/api/admin")
}

export function setOverride(
  original: string,
  replacement: string,
): Promise<{ ok: boolean; overrides: Record<string, string> }> {
  return request("/api/admin/override", {
    method: "POST",
    body: JSON.stringify({ original, replacement }),
  })
}

export function triggerSync(): Promise<SyncResponse> {
  return request<SyncResponse>("/api/admin/sync", { method: "POST" })
}
