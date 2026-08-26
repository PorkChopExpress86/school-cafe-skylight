import { request } from "../../shared/api/request"
import type { SelectResponse, SendResult, WeekResponse } from "./types"

export function getWeek(date?: string): Promise<WeekResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : ""
  return request<WeekResponse>(`/api/week${query}`)
}

export function select(kidId: number, menuDate: string, selection: string): Promise<SelectResponse> {
  return request<SelectResponse>("/api/select", {
    method: "POST",
    body: JSON.stringify({ kid_id: kidId, menu_date: menuDate, selection }),
  })
}

export function sendDay(menuDate: string): Promise<SendResult> {
  return request<SendResult>("/api/send-day", {
    method: "POST",
    body: JSON.stringify({ menu_date: menuDate }),
  })
}

export function sendWeek(date: string): Promise<SendResult> {
  return request<SendResult>("/api/send-week", {
    method: "POST",
    body: JSON.stringify({ date }),
  })
}
