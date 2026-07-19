export type LearningTaskRouteContext = {
  subjectId?: string;
  sessionId?: string;
  pathId?: string;
  stageId?: string;
  taskId?: string;
  sectionId?: string;
  taskType?: string;
  dayId?: string;
  globalDayIndex?: number;
  returnTo?: string;
  legacy?: string;
};

export type CanonicalLearningTaskScope = {
  sessionId: string;
  subjectId: string;
  pathId: string;
  stageId: string;
  dayId: string;
  globalDayIndex: number;
  taskId: string;
  task: any;
  day: any;
  stage: any;
};

export function learningTaskRoute(_type: string, context: LearningTaskRouteContext): string {
  const query = new URLSearchParams(Object.entries(context).filter(([, value]) => value).map(([key, value]) => [key, String(value)])).toString();
  const suffix = query ? `?${query}` : '';
  return `/lecture/section/${encodeURIComponent(context.sectionId || '')}${suffix}`;
}

export function resolveCanonicalLearningTaskScope(path: any, request: LearningTaskRouteContext): CanonicalLearningTaskScope | null {
  const { sessionId = '', subjectId = '', pathId = '', stageId = '', taskId = '', dayId = '', globalDayIndex, taskType } = request;
  if (!sessionId || !subjectId || !pathId || !stageId || !taskId || !dayId || !Number.isFinite(globalDayIndex)) return null;
  if (String(path?.id || path?.path_id || '') !== pathId) return null;
  const stage = (path?.stages || []).find((item: any) => String(item?.id || item?.stage_id || '') === stageId);
  const day = (stage?.days || []).find((item: any) => String(item?.id || item?.dayId || '') === dayId);
  if (!day || Number(day.globalDayIndex) !== globalDayIndex) return null;
  const task = (day.tasks || []).find((item: any) => String(item?.id || item?.task_id || '') === taskId);
  if (!task || (taskType && task.type && task.type !== taskType)) return null;
  return { sessionId, subjectId, pathId, stageId, dayId, globalDayIndex, taskId, task, day, stage };
}
