export interface AdminItem { description: string; category: string; display_description: string }
export interface SyncAttempt { attempted_at: string; succeeded: boolean; weeks_fetched: number; items_stored: number; weeks_covered: string; error: string | null }
export interface AdminResponse { items: AdminItem[]; attempts: SyncAttempt[]; last_success: SyncAttempt | null }
export interface SyncResponse { ok: boolean; message: string }
