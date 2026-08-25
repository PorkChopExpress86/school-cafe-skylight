// TanStack Query hooks for server state.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getAdmin, getWeek, setOverride, triggerLlmCasing, triggerSync } from "../api/client"

export function useWeek(date?: string) {
  return useQuery({
    queryKey: ["week", date ?? "today"],
    queryFn: () => getWeek(date),
  })
}

export function useAdmin() {
  return useQuery({
    queryKey: ["admin"],
    queryFn: getAdmin,
  })
}

export function useOverride() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ original, replacement }: { original: string; replacement: string }) =>
      setOverride(original, replacement),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin"] })
      qc.invalidateQueries({ queryKey: ["week"] })
    },
  })
}

export function useSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerSync,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin"] })
    },
  })
}

export function useLlmCasing() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: triggerLlmCasing,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin"] })
      qc.invalidateQueries({ queryKey: ["week"] })
    },
  })
}
