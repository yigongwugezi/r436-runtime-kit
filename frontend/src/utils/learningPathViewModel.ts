export type PathDisplayMode = 'textbook' | 'daily' | 'project' | 'focus';

export interface PathRouteTarget {
  kind: 'chapter' | 'section' | 'unavailable';
  id?: string;
  stageId?: string;
  chapterId?: string;
  sectionId?: string;
  reason?: string;
}

export interface PathViewItem {
  id?: string;
  title: string;
  goal?: string;
  status?: string;
  estimatedMinutes?: number;
  taskType?: string;
  contentType?: string;
  target: PathRouteTarget;
}

export interface PathViewChapter {
  id?: string;
  title: string;
  items: PathViewItem[];
  target: PathRouteTarget;
}

export interface PathViewStage {
  id?: string;
  ordinal: number;
  title: string;
  description?: string;
  objective?: string;
  estimatedDays?: number;
  estimatedMinutes?: number;
  durationSource: 'stage' | 'items' | 'partial' | 'missing';
  itemCount: number | null;
  completedCount: number | null;
  chapters: PathViewChapter[];
  items: PathViewItem[];
  target: PathRouteTarget;
  availability: 'available' | 'unavailable';
  reason?: string;
}

export interface LearningPathViewModel {
  pathId?: string;
  mode: PathDisplayMode;
  title: string;
  description?: string;
  subject?: string;
  stageCount: number;
  itemCount: number | null;
  completedCount: number | null;
  progress: number | null;
  estimatedMinutes?: number;
  durationSource: 'complete' | 'partial' | 'missing';
  stages: PathViewStage[];
  dataCompleteness: 'complete' | 'partial' | 'empty';
}

const MODES: PathDisplayMode[] = ['textbook', 'daily', 'project', 'focus'];
const doneStatuses = new Set(['mastered', 'completed']);

function array(value: unknown): any[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function idOf(value: any, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const candidate = text(value?.[key]);
    if (candidate) return candidate;
  }
  return undefined;
}

function positiveNumber(value: unknown): number | undefined {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) && number > 0 ? number : undefined;
}

function boundedPercent(value: unknown): number | undefined {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 100 ? number : undefined;
}

function itemFrom(raw: any, stageId?: string, chapterId?: string): PathViewItem {
  const id = idOf(raw, 'id', 'section_id', 'node_id', 'item_id');
  const title = text(raw?.title) || text(raw?.topic) || text(raw?.name) || '未命名学习项';
  const sectionId = id;
  return {
    id,
    title,
    goal: text(raw?.goal) || text(raw?.description) || undefined,
    status: text(raw?.status) || undefined,
    estimatedMinutes: positiveNumber(raw?.estimatedMinutes) ?? positiveNumber(raw?.estimated_minutes) ?? positiveNumber(raw?.duration_minutes) ?? positiveNumber(raw?.duration),
    taskType: text(raw?.task_type) || undefined,
    contentType: text(raw?.contentType) || text(raw?.content_type) || undefined,
    target: sectionId
      ? { kind: 'section', id: sectionId, stageId, chapterId, sectionId }
      : { kind: 'unavailable', stageId, chapterId, reason: '该学习项缺少可导航的原始 ID。' },
  };
}

function chapterFrom(raw: any, stageId?: string): PathViewChapter {
  const id = idOf(raw, 'id', 'chapter_id');
  const items = array(raw?.sections).map((section) => itemFrom(section, stageId, id));
  return {
    id,
    title: text(raw?.title) || '未命名章节',
    items,
    target: id
      ? { kind: 'chapter', id, stageId, chapterId: id }
      : { kind: 'unavailable', stageId, reason: '该章节缺少可导航的原始 ID。' },
  };
}

function modeFrom(raw: any, requested?: string | null): PathDisplayMode {
  if (requested && MODES.includes(requested as PathDisplayMode)) return requested as PathDisplayMode;
  const explicit = text(raw?.path_mode) || text(raw?.plan_mode);
  if (MODES.includes(explicit as PathDisplayMode)) return explicit as PathDisplayMode;
  for (const stage of array(raw?.stages)) {
    const stageMode = text(stage?.path_mode) || text(stage?.plan_mode);
    if (MODES.includes(stageMode as PathDisplayMode)) return stageMode as PathDisplayMode;
    const firstSection = array(stage?.chapters)[0]?.sections?.[0];
    if (text(firstSection?.task_type)) return 'daily';
  }
  return 'textbook';
}

function stageFrom(raw: any, index: number, rootNodes: any[]): PathViewStage {
  const id = idOf(raw, 'id', 'stage_id');
  const chapters = array(raw?.chapters).map((chapter) => chapterFrom(chapter, id));
  const directSections = array(raw?.sections).map((section) => itemFrom(section, id));
  const stageNodes = array(raw?.nodes);
  const rootItems = stageNodes.length === 0 && chapters.length === 0 && directSections.length === 0
    ? rootNodes.filter((node) => text(node?.related_stage_id) === id || text(node?.relatedStageId) === id)
    : [];
  // Chapter sections are the canonical display source. The backend also emits
  // flattened nodes for backwards compatibility; counting both duplicates items.
  const directItems = directSections.length > 0
    ? directSections
    : chapters.length > 0
      ? []
      : [...stageNodes.map((node) => itemFrom(node, id)), ...rootItems.map((node) => itemFrom(node, id))];
  const taskItems = directItems.length === 0 && chapters.length === 0
    ? array(raw?.items).map((item) => itemFrom(item, id)).concat(array(raw?.tasks).map((task) => itemFrom({ title: task }, id)))
    : [];
  const items = [...chapters.flatMap((chapter) => chapter.items), ...directItems, ...taskItems];
  const hasItemSource = chapters.length > 0 || directSections.length > 0 || stageNodes.length > 0 || rootItems.length > 0 || array(raw?.items).length > 0 || array(raw?.tasks).length > 0;
  const statusKnown = items.length > 0 && items.every((item) => Boolean(item.status));
  const itemMinutes = items.map((item) => item.estimatedMinutes).filter((value): value is number => value !== undefined);
  const stageMinutes = positiveNumber(raw?.estimatedMinutes) ?? positiveNumber(raw?.estimated_minutes) ?? positiveNumber(raw?.duration_minutes);
  const estimatedMinutes = stageMinutes ?? (itemMinutes.length === items.length && items.length > 0 ? itemMinutes.reduce((sum, value) => sum + value, 0) : undefined);
  const availability = id || items.some((item) => item.target.kind !== 'unavailable') ? 'available' : 'unavailable';
  return {
    id,
    ordinal: positiveNumber(raw?.order) ?? positiveNumber(raw?.ordinal) ?? index + 1,
    title: text(raw?.title) || `阶段 ${index + 1}`,
    description: text(raw?.description) || undefined,
    objective: text(raw?.objective) || text(raw?.goal) || undefined,
    estimatedDays: positiveNumber(raw?.estimatedDays) ?? positiveNumber(raw?.estimated_days),
    estimatedMinutes,
    durationSource: stageMinutes !== undefined ? 'stage' : estimatedMinutes !== undefined ? 'items' : itemMinutes.length > 0 ? 'partial' : 'missing',
    itemCount: hasItemSource && items.length > 0 ? items.length : null,
    completedCount: statusKnown ? items.filter((item) => doneStatuses.has(item.status || '')).length : null,
    chapters,
    items: directItems.length > 0 ? directItems : taskItems,
    target: id ? { kind: 'unavailable', stageId: id, reason: '请选择章节或学习项进入内容。' } : { kind: 'unavailable', reason: '该阶段缺少可导航的原始 ID。' },
    availability,
    reason: availability === 'unavailable' ? '该阶段缺少可导航的原始 ID。' : undefined,
  };
}

export function summarizePathText(value: unknown, limit = 160): string {
  const normalized = text(value).replace(/\s+/g, ' ');
  return normalized.length > limit ? `${normalized.slice(0, limit)}…` : normalized;
}

export function adaptLearningPath(raw: any, requestedMode?: string | null): LearningPathViewModel {
  const rootNodes = array(raw?.nodes);
  const stages = array(raw?.stages).map((stage, index) => stageFrom(stage, index, rootNodes));
  const completeItemCounts = stages.every((stage) => stage.itemCount !== null);
  const completeProgress = stages.every((stage) => stage.completedCount !== null);
  const itemCount = stages.length > 0 && completeItemCounts ? stages.reduce((sum, stage) => sum + (stage.itemCount || 0), 0) : null;
  const completedCount = itemCount !== null && completeProgress ? stages.reduce((sum, stage) => sum + (stage.completedCount || 0), 0) : null;
  const rawProgress = boundedPercent(raw?.overallProgress) ?? boundedPercent(raw?.overall_progress);
  const progress = itemCount && completedCount !== null ? Math.round((completedCount / itemCount) * 100) : rawProgress !== undefined && itemCount !== null ? rawProgress : null;
  const knownDurations = stages.map((stage) => stage.estimatedMinutes).filter((value): value is number => value !== undefined);
  const durationSource = knownDurations.length === 0 ? 'missing' : knownDurations.length === stages.length ? 'complete' : 'partial';
  return {
    pathId: idOf(raw, 'id', 'path_id'),
    mode: modeFrom(raw, requestedMode),
    title: text(raw?.title) || text(raw?.courseName) || text(raw?.course_name) || '学习路径',
    description: text(raw?.description) || undefined,
    subject: text(raw?.courseName) || text(raw?.course_name) || undefined,
    stageCount: stages.length,
    itemCount,
    completedCount,
    progress,
    estimatedMinutes: knownDurations.length > 0 ? knownDurations.reduce((sum, value) => sum + value, 0) : undefined,
    durationSource,
    stages,
    dataCompleteness: stages.length === 0 ? 'empty' : completeItemCounts && durationSource === 'complete' ? 'complete' : 'partial',
  };
}

/**
 * Keep the existing page consumers on their camelCase contract without
 * synthesising nodes or identifiers for older stored paths.
 */
export function normalizeLearningPathForClient(raw: any): any {
  if (!raw || typeof raw !== 'object') return raw;
  const normalizeSection = (section: any) => ({
    ...section,
    id: idOf(section, 'id', 'section_id'),
    title: text(section?.title),
    goal: text(section?.goal) || text(section?.description),
    estimatedMinutes: positiveNumber(section?.estimatedMinutes) ?? positiveNumber(section?.estimated_minutes),
    knowledgePoints: array(section?.knowledgePoints).length > 0 ? array(section?.knowledgePoints) : array(section?.knowledge_points).map((point) => ({ ...point, id: idOf(point, 'id', 'kp_id'), name: text(point?.name) })),
    lectureIds: array(section?.lectureIds),
    contentType: text(section?.contentType) || text(section?.content_type) || undefined,
  });
  const normalizeChapter = (chapter: any) => ({
    ...chapter,
    id: idOf(chapter, 'id', 'chapter_id'),
    title: text(chapter?.title),
    order: positiveNumber(chapter?.order) ?? 0,
    sections: array(chapter?.sections).map(normalizeSection),
  });
  const normalizeNode = (node: any) => ({
    ...node,
    id: idOf(node, 'id', 'node_id'),
    topic: text(node?.topic) || text(node?.title) || text(node?.name),
  });
  // Normalize stages: flatten days→tasks for new format
  const _stages = array(raw?.stages).map((stage: any) => ({
    ...stage,
    tasks: array(stage?.days).length > 0
      ? array(stage.days).flatMap((day: any) => array(day?.tasks))
      : array(stage?.tasks),
  }));
  const _raw = { ...raw, stages: _stages };
  return {
    ...raw,
    id: idOf(raw, 'id', 'path_id'),
    title: text(raw?.title),
    description: text(raw?.description),
    courseName: text(raw?.courseName) || text(raw?.course_name),
    overallProgress: boundedPercent(raw?.overallProgress) ?? boundedPercent(raw?.overall_progress),
    estimatedDays: positiveNumber(raw?.estimatedDays) ?? positiveNumber(raw?.estimated_days),
    stages: array(_raw?.stages).map((stage, index) => ({
      ...stage,
      id: idOf(stage, 'id', 'stage_id'),
      order: positiveNumber(stage?.order) ?? index + 1,
      title: text(stage?.title) || `阶段 ${index + 1}`,
      description: text(stage?.description),
      objective: text(stage?.objective) || text(stage?.goal),
      estimatedDays: positiveNumber(stage?.estimatedDays) ?? positiveNumber(stage?.estimated_days),
      chapters: array(stage?.chapters).map(normalizeChapter),
      sections: array(stage?.sections).map(normalizeSection),
      nodes: array(stage?.nodes).map(normalizeNode),

      // 后端 _task_stages_to_frontend 已展平 days.tasks → 前端不再重复展平
      days: array(stage?.days),
      tasks: array(stage?.tasks || []).map((task: any) => ({
        ...task,
        task_id: task.task_id || task.taskId || task.id || "",
        title: task.title || "",
        type: task.type || task.task_type || "read_doc",
        goal: task.goal || task.description || "",
        estimated_minutes: task.estimated_minutes ?? task.estimatedMinutes ?? 30,
        required: task.required !== false,
        resource_types: task.resource_types || task.resourceTypes || [],
        status: task.status || "pending",
        source: task.source || "textbook",
        _adjustment: task._adjustment || "",
        _adjustment_reason: task._adjustment_reason || "",
      })),
    })),
  };
}
