import { useQuery } from "@tanstack/react-query"
import { getWeek } from "./api"
import { plannerQueryKeys } from "./queryKeys"

export function useWeek(date?: string) {
  return useQuery({ queryKey: plannerQueryKeys.week(date), queryFn: () => getWeek(date) })
}
