export type TaskExecutionMode = 'lecture' | 'video' | 'quiz' | 'practice' | 'mindmap' | 'unsupported';

export function resolveTaskExecutionMode(task: any): TaskExecutionMode {
  const type = String(task?.task_type || task?.taskType || task?.type || task?.resource_type || '').toLowerCase();
  if (['read_doc', 'lecture', 'reading'].includes(type)) return 'lecture';
  if (['video', 'watch_video'].includes(type)) return 'video';
  if (['quiz', 'do_quiz', 'quiz_prac', 'assessment', 'test'].includes(type)) return 'quiz';
  if (['code', 'coding', 'practice'].includes(type)) return 'practice';
  if (['mind_map', 'mindmap'].includes(type)) return 'mindmap';
  return type ? 'unsupported' : 'lecture';
}
