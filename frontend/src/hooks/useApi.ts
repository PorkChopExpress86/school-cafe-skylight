// TanStack Query hooks for server state.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getAdmin, getWeek, select, sendDay, sendWeek, setOverride, triggerLlmCasing, triggerSync } from "../api/client"

export function useWeek(date?: string) {
  return useQuery({
    queryKey: ["week", date ?? "today"],
    queryFn: () => getWeek(date),
  })
}

export function useSelect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kid_id, menu_date, selection }: { kid_id: number; menu_date: string; selection: string }) =>
      select(kid_id, menu_date, selection),
    onSuccess: () => {
      // Refresh the week view (selections, counts, history).
      qc.invalidateQueries({ queryKey: ["week"] })
    },
  })
}

export function useSendDay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (menu_date: string) => sendDay(menu_date),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["week"] })
    },
  })
}

export function useSendWeek() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (date: string) => sendWeek(date),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["week"] })
    },
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
