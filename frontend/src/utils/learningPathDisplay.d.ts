export function normalizePathForDisplay(path: unknown): { path: any; stages: any[]; formatInvalid: boolean };
export function groupTasksByDay(stages: unknown): { stageId: string; stageTitle: string; stageIdx: number; days: { dayId: string; dayIndex: number; globalDayIndex: number; tasks: any[]; stageIdx: number }[] }[];
export function restoreSelectedDay(dayGroups: unknown, activeDayKey: string | null): { expandedStageId: string | null; activeDayKey: string | null };
