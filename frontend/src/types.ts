// Shared types matching the FastAPI JSON responses.

export const MAKE_AT_HOME = "__MAKE_AT_HOME__"

export interface Kid {
  id: number
  name: string
  color: string
  prefix: string
}

export interface SelectionState {
  selection: string
  sent_at: string | null
  sent_sitting_id: string | null
  publication_state: SelectionPublicationState
}

export type SelectionPublicationState = "pending" | "published" | "make_at_home"

export interface DayMenu {
  date: string
  weekday: string
  entrees: string[]
}

export interface HistoryItem {
  id: number
  kid_name: string
  menu_date: string
  selection: string
  action: string
  created_at: string
}

export interface SchoolConfig {
  school_id: string
  serving_line: string
  meal_type: string
  grade: string
}

export interface SkylightConfig {
  email: string
  frame_id: string
}

export interface WeekResponse {
  week: DayMenu[]
  kids: Kid[]
  selections: Record<string, Record<number, SelectionState>>
  day_totals: Record<string, number>
  day_sent: Record<string, number>
  history: HistoryItem[]
  ref: string
  prev_week: string
  next_week: string
  today: string
  school_cfg: SchoolConfig | null
  skylight_cfg: SkylightConfig | null
  menu_error: string | null
}

export interface SelectResponse {
  kid_id: number
  menu_date: string
  selection: string
  sent_at: string | null
  day_totals: Record<string, number>
  day_sent: Record<string, number>
  history: HistoryItem[]
}

export interface SendResult {
  ok: boolean
  message: string
  sent: number
  deleted: number
  skipped: number
  errors: string[]
  results: PublicationKidResult[]
  day_totals?: Record<string, number>
  day_sent?: Record<string, number>
  history?: HistoryItem[]
}

export type PlannerPublicationStatus = "sent" | "skipped" | "error"

export interface PublicationKidResult {
  kid_name: string
  menu_date?: string
  selection: string
  status: PlannerPublicationStatus
}

export interface AdminItem {
  description: string
  category: string
  display_description: string
}

export interface SyncAttempt {
  attempted_at: string
  succeeded: boolean
  weeks_fetched: number
  items_stored: number
  weeks_covered: string
  error: string | null
}

export interface AdminResponse {
  items: AdminItem[]
  attempts: SyncAttempt[]
  last_success: SyncAttempt | null
}

export interface SyncResponse {
  ok: boolean
  message: string
}
