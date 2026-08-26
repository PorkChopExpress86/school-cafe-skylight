import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { plannerQueryKeys } from "../planner/queryKeys"
import { getAdmin, setOverride, triggerLlmCasing, triggerSync } from "./api"
import { menuCatalogQueryKeys } from "./queryKeys"

export function useAdmin() {
  return useQuery({ queryKey: menuCatalogQueryKeys.root, queryFn: getAdmin })
}

export function useOverride() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ original, replacement }: { original: string; replacement: string }) => setOverride(original, replacement),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: menuCatalogQueryKeys.root })
      void queryClient.invalidateQueries({ queryKey: plannerQueryKeys.weeks })
    },
  })
}

export function useSync() {
  const queryClient = useQueryClient()
  return useMutation({ mutationFn: triggerSync, onSuccess: () => void queryClient.invalidateQueries({ queryKey: menuCatalogQueryKeys.root }) })
}

export function useLlmCasing() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: triggerLlmCasing,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: menuCatalogQueryKeys.root })
      void queryClient.invalidateQueries({ queryKey: plannerQueryKeys.weeks })
    },
  })
}
