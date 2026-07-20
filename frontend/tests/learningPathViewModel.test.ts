import assert from 'node:assert/strict';
import { adaptLearningPath, normalizeLearningPathForClient, summarizePathText } from '../src/utils/learningPathViewModel.ts';

const legacy = adaptLearningPath({
  id: 'path-old', title: '旧版路径', stages: [{
    stage_id: 'stage-old', title: '基础', chapters: [{
      chapter_id: 'chapter-old', title: '第一章', sections: [{ section_id: 'section-old', title: '数组', estimated_minutes: 25, status: 'mastered' }],
    }],
  }],
});
assert.equal(legacy.mode, 'textbook');
assert.equal(legacy.stageCount, 1);
assert.equal(legacy.itemCount, 1);
assert.equal(legacy.completedCount, 1);
assert.equal(legacy.stages[0].chapters[0].target.id, 'chapter-old');
assert.equal(legacy.stages[0].chapters[0].items[0].target.id, 'section-old');
assert.equal(legacy.estimatedMinutes, 25);

const normalizedLegacy = normalizeLearningPathForClient({ stages: [{ stage_id: 'stage-route', chapters: [{ chapter_id: 'chapter-route', sections: [{ section_id: 'section-route', title: '可路由小节' }] }] }] });
assert.equal(normalizedLegacy.stages[0].id, 'stage-route');
assert.equal(normalizedLegacy.stages[0].chapters[0].id, 'chapter-route');
assert.equal(normalizedLegacy.stages[0].chapters[0].sections[0].id, 'section-route');
assert.deepEqual(normalizedLegacy.stages[0].nodes, [], 'normalization must not invent compatibility nodes');

const dailyRaw = { stages: [{ id: 'daily-stage', days: [{ tasks: [{ id: 'daily-task' }] }] }] };
normalizeLearningPathForClient(dailyRaw);
assert.equal(dailyRaw.stages[0].tasks, undefined, 'normalization must not mutate the API response');

const hierarchyWithLegacyNodes = adaptLearningPath({ stages: [{ id: 'stage-hybrid', chapters: [{ id: 'chapter-hybrid', sections: [{ id: 'section-hybrid', title: '唯一小节' }] }], nodes: [{ id: 'legacy-kp', topic: '不应重复计数' }] }] });
assert.equal(hierarchyWithLegacyNodes.itemCount, 1, 'chapter hierarchy must take precedence over compatibility nodes');

const current = adaptLearningPath({
  path_mode: 'daily', stages: Array.from({ length: 5 }, (_, stage) => ({
    id: `stage-${stage}`, estimatedDays: 0.5, nodes: Array.from({ length: 4 }, (_, item) => ({
      id: `node-${stage}-${item}`, topic: `主题 ${stage}-${item}`, duration: 10, status: item === 0 ? 'completed' : 'available',
    })),
  })),
});
assert.equal(current.mode, 'daily');
assert.equal(current.stageCount, 5);
assert.equal(current.itemCount, 20);
assert.equal(current.completedCount, 5);
assert.equal(current.stages[0].items[0].target.id, 'node-0-0');
assert.equal(current.stages.reduce((sum, stage) => sum + (stage.estimatedDays || 0), 0), 2.5, 'actual estimated days must not be replaced with a fixed duration');

const twoDay = adaptLearningPath({ stages: Array.from({ length: 4 }, (_, index) => ({ id: `two-day-${index}`, estimatedDays: 0.5, nodes: [{ id: `two-day-node-${index}`, topic: '学习项' }] })) });
assert.equal(twoDay.stages.reduce((sum, stage) => sum + (stage.estimatedDays || 0), 0), 2);

const missing = adaptLearningPath({ stages: [{ id: 'stage-missing', nodes: [{ id: 'node-missing', topic: '无时长' }] }] });
assert.equal(missing.stages[0].itemCount, 1);
assert.equal(missing.stages[0].completedCount, null);
assert.equal(missing.stages[0].estimatedMinutes, undefined);
assert.equal(missing.durationSource, 'missing');

const partial = adaptLearningPath({ stages: [{ id: 'stage-partial', nodes: [{ id: 'node-one', topic: '有时长', duration: 15 }, { id: 'node-two', topic: '无时长' }] }] });
assert.equal(partial.stages[0].estimatedMinutes, undefined);
assert.equal(partial.stages[0].durationSource, 'partial');

const flat = adaptLearningPath({ stages: [{ id: 'stage-flat', title: '扁平阶段' }], nodes: [{ id: 'flat-section', related_stage_id: 'stage-flat', title: '扁平小节', estimated_minutes: 30, status: 'available' }] });
assert.equal(flat.stages[0].items[0].target.id, 'flat-section');

const empty = adaptLearningPath({ stages: [] });
assert.equal(empty.dataCompleteness, 'empty');
assert.equal(empty.itemCount, null);
const emptyStage = adaptLearningPath({ stages: [{ id: 'empty-stage' }] });
assert.equal(emptyStage.stages[0].itemCount, null);
assert.equal(emptyStage.stages[0].estimatedMinutes, undefined);
assert.doesNotThrow(() => adaptLearningPath({ stages: [{ id: 'malformed', nodes: [null, 'not-an-object'] }] }));
assert.equal(adaptLearningPath({ path_mode: 'unknown', stages: [] }).mode, 'textbook');
assert.equal(adaptLearningPath({ stages: [] }, 'project').mode, 'project');
assert.equal(summarizePathText('a'.repeat(200), 20), `${'a'.repeat(20)}…`);

console.log('learning path view model tests: ok');
