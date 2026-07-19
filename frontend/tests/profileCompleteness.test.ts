import assert from 'node:assert/strict';
import { isSpecificLearningGoal, isUsableProfileValue, profileCompleteness, profileDisplayCompleteness } from '../src/utils/profileCompleteness.ts';

const keys = ['background', 'target_course', 'knowledge_base', 'weak_points', 'learning_goal', 'time_budget', 'preference'];
assert.equal(profileCompleteness({ target_course: '数据结构' }, keys), 1);
assert.equal(Math.round(profileCompleteness({ target_course: '数据结构' }, keys) / keys.length * 100), 14);
for (const value of ['未明确说明', '暂无诊断信息', 'unknown', '']) assert.equal(isUsableProfileValue(value), false);
assert.equal(isSpecificLearningGoal('规划数据结构学习'), false);
assert.equal(profileCompleteness({ target_course: '数据结构', learning_goal: '考研', time_budget: '每天一小时', background: '软件工程大二' }, keys), 4);
assert.deepEqual(profileDisplayCompleteness({ learning_goal: '复习', daily_minutes: 60, background: '大二', learning_history: '待补充', prior_experience: ['C 语言'], content_preferences: ['example_first'], resource_preferences: [] }), { filled: 5, total: 7, percent: 71 });
assert.deepEqual(profileDisplayCompleteness({ learning_goal: '复习', daily_minutes: 60, background: '大二', learning_history: '学过 C 语言', prior_experience: ['C 语言'], content_preferences: ['example_first'], resource_preferences: ['视频'] }), { filled: 7, total: 7, percent: 100 });
console.log('profile completeness tests: ok');
