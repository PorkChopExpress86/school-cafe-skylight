import { useMemo, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { select, sendDay, sendWeek } from "../api/client"
import type { SendResult } from "../types"

export interface PlannerDayInteraction {
  result: SendResult | null
  isChangingSelection: boolean
  isPublishing: boolean
  onSelectionChange: (kidId: number, menuDate: string, selection: string) => void
  onPublication: (menuDate: string) => void
}

export interface PlannerWeekInteraction {
  result: SendResult | null
  isPublishing: boolean
  onPublication: (referenceDate: string) => void
}

export interface PlannerInteractionState {
  week: PlannerWeekInteraction
  forDate: (menuDate: string) => PlannerDayInteraction
}

export function usePlannerInteraction(): PlannerInteractionState {
  const queryClient = useQueryClient()
  const [dayPublicationResults, setDayPublicationResults] = useState<Record<string, SendResult>>({})
  const selectionChange = useMutation({
    mutationFn: ({ kidId, menuDate, selection }: { kidId: number; menuDate: string; selection: string }) =>
      select(kidId, menuDate, selection),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["week"] }),
  })
  const dayPublication = useMutation({
    mutationFn: sendDay,
    onSuccess: (result, menuDate) => {
      setDayPublicationResults((previous) => ({ ...previous, [menuDate]: result }))
      void queryClient.invalidateQueries({ queryKey: ["week"] })
    },
  })
  const weekPublication = useMutation({
    mutationFn: sendWeek,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["week"] }),
  })
  const { isPending: isChangingSelection, mutate: changeSelection } = selectionChange
  const { isPending: isPublishingDay, mutate: publishDay } = dayPublication
  const { data: weekPublicationResult, isPending: isPublishingWeek, mutate: publishWeek } = weekPublication

  return useMemo(() => {
    const dates = new Map<string, PlannerDayInteraction>()
    return {
      week: {
        result: weekPublicationResult ?? null,
        isPublishing: isPublishingWeek,
        onPublication: publishWeek,
      },
      forDate: (menuDate: string) => {
        const existing = dates.get(menuDate)
        if (existing) return existing

        const interaction = {
          result: dayPublicationResults[menuDate] ?? null,
          isChangingSelection,
          isPublishing: isPublishingDay,
          onSelectionChange: (kidId: number, selectedDate: string, selection: string) =>
            changeSelection({ kidId, menuDate: selectedDate, selection }),
          onPublication: publishDay,
        }
        dates.set(menuDate, interaction)
        return interaction
      },
    }
  }, [
    changeSelection,
    dayPublicationResults,
    isChangingSelection,
    isPublishingDay,
    isPublishingWeek,
    publishDay,
    publishWeek,
    weekPublicationResult,
  ])
}
