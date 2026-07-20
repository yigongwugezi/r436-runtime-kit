const array = (value) => Array.isArray(value) ? value : [];

const dayNumber = (day, fallback) => {
  const value = Number(day?.day ?? day?.day_index ?? day?.dayIndex);
  return Number.isFinite(value) && value > 0 ? value : fallback;
};

export function normalizePathForDisplay(path) {
  const source = path && typeof path === 'object' && !Array.isArray(path) ? path : {};
  let formatInvalid = Boolean(path && source !== path) || (source.stages !== undefined && !Array.isArray(source.stages));
  const stages = array(source.stages).map((rawStage, stageIndex) => {
    if (!rawStage || typeof rawStage !== 'object' || Array.isArray(rawStage)) {
      formatInvalid = true;
      return null;
    }
    const rawDays = rawStage.days;
    const rawTasks = rawStage.tasks;
    if (rawDays !== undefined && !Array.isArray(rawDays)) formatInvalid = true;
    if (rawTasks !== undefined && !Array.isArray(rawTasks)) formatInvalid = true;
    let days;
    if (Array.isArray(rawDays)) {
      days = rawDays.map((rawDay, dayIndex) => {
        if (!rawDay || typeof rawDay !== 'object' || Array.isArray(rawDay)) {
          formatInvalid = true;
          return { dayIndex: dayIndex + 1, tasks: [] };
        }
        if (rawDay.tasks !== undefined && !Array.isArray(rawDay.tasks)) formatInvalid = true;
        return { ...rawDay, dayIndex: dayNumber(rawDay, dayIndex + 1), tasks: array(rawDay.tasks).slice() };
      });
    } else {
      if (array(rawTasks).length) formatInvalid = true;
      days = [];
    }
    const tasks = days.flatMap((day) => {
      const dayId = String(day?.id || day?.dayId || '');
      const globalDayIndex = Number(day?.globalDayIndex) || day.dayIndex;
      return day.tasks.map((task) => ({ ...task, dayId, globalDayIndex }));
    });
    return { ...rawStage, id: rawStage.id || rawStage.stage_id || `stage-${stageIndex}`, days, tasks };
  }).filter(Boolean);
  return { path: { ...source, stages }, stages, formatInvalid };
}

export function groupTasksByDay(stages) {
  return array(stages).map((stage, stageIdx) => ({
    stageId: String(stage?.id || stage?.stage_id || `stage-${stageIdx}`),
    stageTitle: String(stage?.title || `阶段 ${stageIdx + 1}`),
    stageProgressStatus: stage?.progressStatus,
    stageIdx,
    days: array(stage?.days).map((day, dayIdx) => {
      const dayId = String(day?.id || day?.dayId || '');
      const globalDayIndex = Number(day?.globalDayIndex) || dayNumber(day, dayIdx + 1);
      return {
        ...day, dayId, dayIndex: dayNumber(day, dayIdx + 1), globalDayIndex,
        tasks: array(day?.tasks).map((task) => ({ ...task, dayId, globalDayIndex })), stageIdx,
      };
    }),
  }));
}

export function isTaskLocked(stage, day, tasks, taskIndex) {
  if (stage?.progressStatus === 'locked' || day?.progressStatus === 'locked') return true;
  if (stage?.progressStatus === 'completed' || day?.progressStatus === 'completed') return false;
  const firstIncomplete = array(tasks).findIndex((task) => task?.status !== 'completed' && task?.status !== 'mastered');
  return firstIncomplete >= 0 && taskIndex > firstIncomplete;
}

export function restoreSelectedDay(dayGroups, activeDayKey) {
  const groups = array(dayGroups);
  const selectable = groups.filter((group) => array(group.days).length > 0);
  const days = selectable.flatMap((group) => array(group.days).map((day) => ({ group, day })));
  const active = days.find(({ group, day }) => `${group.stageId}_day${day.dayIndex}` === activeDayKey && day.progressStatus !== 'locked');
  if (active) return { expandedStageId: active.group.stageId, activeDayKey };
  const target = days.find(({ group, day }) => group.stageProgressStatus === 'current' && day.progressStatus === 'current')
    || days.find(({ group, day }) => group.stageProgressStatus === 'current' && day.progressStatus !== 'locked')
    || days.find(({ day }) => day.progressStatus !== 'locked');
  return target
    ? { expandedStageId: target.group.stageId, activeDayKey: `${target.group.stageId}_day${target.day.dayIndex}` }
    : { expandedStageId: groups[0]?.stageId || null, activeDayKey: null };
}
