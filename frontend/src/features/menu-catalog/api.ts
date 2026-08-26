import { request } from "../../shared/api/request"
import type { AdminResponse, CasingResponse, SyncResponse } from "./types"

export function getAdmin(): Promise<AdminResponse> {
  return request<AdminResponse>("/api/admin")
}

export function setOverride(original: string, replacement: string): Promise<{ ok: boolean }> {
  return request("/api/admin/override", { method: "POST", body: JSON.stringify({ original, replacement }) })
}

export function triggerSync(): Promise<SyncResponse> {
  return request<SyncResponse>("/api/admin/sync", { method: "POST" })
}

export function triggerLlmCasing(): Promise<CasingResponse> {
  return request("/api/admin/llm-case-all", { method: "POST" })
}
