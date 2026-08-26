import { useQuery } from "@tanstack/react-query"
import { getMonth, getWeek } from "./api"
import { plannerQueryKeys } from "./queryKeys"

export function useWeek(date?: string) {
  return useQuery({ queryKey: plannerQueryKeys.week(date), queryFn: () => getWeek(date) })
}

export function useMonth(month?: string) {
  return useQuery({ queryKey: plannerQueryKeys.month(month), queryFn: () => getMonth(month) })
}
