import assert from 'node:assert/strict';
import { isSpecificLearningGoal, isUsableProfileValue, profileCompleteness } from '../src/utils/profileCompleteness.ts';

const keys = ['background', 'target_course', 'knowledge_base', 'weak_points', 'learning_goal', 'time_budget', 'preference'];
assert.equal(profileCompleteness({ target_course: '数据结构' }, keys), 1);
assert.equal(Math.round(profileCompleteness({ target_course: '数据结构' }, keys) / keys.length * 100), 14);
for (const value of ['未明确说明', '暂无诊断信息', 'unknown', '']) assert.equal(isUsableProfileValue(value), false);
assert.equal(isSpecificLearningGoal('规划数据结构学习'), false);
assert.equal(profileCompleteness({ target_course: '数据结构', learning_goal: '考研', time_budget: '每天一小时', background: '软件工程大二' }, keys), 4);
console.log('profile completeness tests: ok');
