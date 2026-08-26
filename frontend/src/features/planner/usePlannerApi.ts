import { useQuery } from "@tanstack/react-query"
import { getMonth, getWeek } from "./api"
import { plannerQueryKeys } from "./queryKeys"

export function useWeek(date?: string) {
  return useQuery({ queryKey: plannerQueryKeys.week(date), queryFn: () => getWeek(date) })
}

export function useMonth() {
  return useQuery({ queryKey: plannerQueryKeys.month, queryFn: getMonth })
}
