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
    const tasks = days.flatMap((day) => day.tasks);
    return { ...rawStage, id: rawStage.id || rawStage.stage_id || `stage-${stageIndex}`, days, tasks };
  }).filter(Boolean);
  return { path: { ...source, stages }, stages, formatInvalid };
}

export function groupTasksByDay(stages) {
  return array(stages).map((stage, stageIdx) => ({
    stageId: String(stage?.id || stage?.stage_id || `stage-${stageIdx}`),
    stageTitle: String(stage?.title || `阶段 ${stageIdx + 1}`),
    stageIdx,
    days: array(stage?.days).map((day, dayIdx) => ({
      dayIndex: dayNumber(day, dayIdx + 1), globalDayIndex: Number(day?.globalDayIndex) || dayNumber(day, dayIdx + 1), tasks: array(day?.tasks), stageIdx,
    })),
  }));
}

export function restoreSelectedDay(dayGroups, activeDayKey) {
  const groups = array(dayGroups);
  const selectable = groups.filter((group) => array(group.days).length > 0);
  const active = selectable.find((group) => array(group.days).some((day) => `${group.stageId}_day${day.dayIndex}` === activeDayKey));
  if (active) return { expandedStageId: active.stageId, activeDayKey };
  const target = selectable.find((group) => array(group.days).some((day) => array(day.tasks).some((task) => task.status !== 'completed' && task.status !== 'mastered'))) || selectable[0];
  return target ? { expandedStageId: target.stageId, activeDayKey: `${target.stageId}_day${target.days[0].dayIndex}` } : { expandedStageId: groups[0]?.stageId || null, activeDayKey: null };
}
