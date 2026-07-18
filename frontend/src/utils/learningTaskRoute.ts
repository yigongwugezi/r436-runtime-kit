export type LearningTaskRouteContext = {
  subjectId?: string;
  sessionId?: string;
  pathId?: string;
  stageId?: string;
  taskId?: string;
  sectionId?: string;
  returnTo?: string;
};

export function learningTaskRoute(type: string, context: LearningTaskRouteContext): string {
  const query = new URLSearchParams(Object.entries(context).filter(([, value]) => value).map(([key, value]) => [key, String(value)])).toString();
  const suffix = query ? `?${query}` : '';
  if (['reading', 'document', 'lecture', 'read_doc'].includes(type)) return `/lecture/section/${encodeURIComponent(context.sectionId || context.taskId || '')}${suffix}`;
  if (['quiz', 'practice', 'exam', 'do_quiz'].includes(type)) return `/practice${suffix}`;
  if (type === 'mindmap') return `/knowledge-graph${suffix}`;
  if (type === 'resource') return `/resources${suffix}`;
  return `/learning-path${suffix}`;
}
