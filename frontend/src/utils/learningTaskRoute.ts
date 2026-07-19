export type LearningTaskRouteContext = {
  subjectId?: string;
  sessionId?: string;
  pathId?: string;
  stageId?: string;
  taskId?: string;
  sectionId?: string;
  taskType?: string;
  returnTo?: string;
  legacy?: string;
};

export function learningTaskRoute(_type: string, context: LearningTaskRouteContext): string {
  const query = new URLSearchParams(Object.entries(context).filter(([, value]) => value).map(([key, value]) => [key, String(value)])).toString();
  const suffix = query ? `?${query}` : '';
  return `/lecture/section/${encodeURIComponent(context.sectionId || context.taskId || '')}${suffix}`;
}
