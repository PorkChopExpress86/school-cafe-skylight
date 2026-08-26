export const plannerQueryKeys = {
  weeks: ["week"] as const,
  week: (date?: string) => ["week", date ?? "today"] as const,
  month: ["week", "month"] as const,
}
