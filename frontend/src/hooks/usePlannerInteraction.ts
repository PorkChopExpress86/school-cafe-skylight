import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { select, sendDay, sendWeek } from "../api/client"
import type { SendResult } from "../types"

export interface PlannerDayInteraction {
  result: SendResult | null
  isPublishing: boolean
  onSelectionChange: (kidId: number, menuDate: string, selection: string) => void
  onPublication: (menuDate: string) => void
}

export function usePlannerInteraction() {
  const queryClient = useQueryClient()
  const [dayPublicationResults, setDayPublicationResults] = useState<Record<string, SendResult>>({})
  const selectionChange = useMutation({
    mutationFn: ({ kidId, menuDate, selection }: { kidId: number; menuDate: string; selection: string }) =>
      select(kidId, menuDate, selection),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["week"] }),
  })
  const dayPublication = useMutation({
    mutationFn: sendDay,
    onSuccess: (result, menuDate) => {
      setDayPublicationResults((previous) => ({ ...previous, [menuDate]: result }))
      queryClient.invalidateQueries({ queryKey: ["week"] })
    },
  })
  const weekPublication = useMutation({
    mutationFn: sendWeek,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["week"] }),
  })

  return {
    publishDay: dayPublication.mutate,
    publishWeek: weekPublication.mutate,
    isChangingSelection: selectionChange.isPending,
    isPublishingDay: dayPublication.isPending,
    isPublishingWeek: weekPublication.isPending,
    weekPublicationResult: weekPublication.data,
    dayInteraction: (menuDate: string): PlannerDayInteraction => ({
      result: dayPublicationResults[menuDate] ?? null,
      isPublishing: dayPublication.isPending,
      onSelectionChange: (kidId, selectedDate, selection) =>
        selectionChange.mutate({ kidId, menuDate: selectedDate, selection }),
      onPublication: dayPublication.mutate,
    }),
  }
}
