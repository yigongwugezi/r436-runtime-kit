import assert from 'node:assert/strict';
import { ensureScopedLearningPathQuiz, learningPathQuizScope, normalizeLearningPathQuiz, retryScopedLearningPathQuiz } from '../src/utils/learningPathQuiz.ts';

const scope = { sessionId: 's', subjectId: 'sub', pathId: 'p', stageId: 'stage', dayId: 'd3', globalDayIndex: 3, taskId: 'quiz' };
assert.equal(learningPathQuizScope(scope), 's|sub|p|stage|d3|3|quiz|quiz');
assert.deepEqual(normalizeLearningPathQuiz({ data: { quiz: { quizId: 'q', question_count: 1, questions: [{ question_id: 'q1', stem: '题目' }] } } }), { quizId: 'q', questionCount: 1, questions: [{ question_id: 'q1', questionId: 'q1', stem: '题目' }] });
assert.equal(normalizeLearningPathQuiz({ quiz: { quiz_id: 'q2', questions: [{ id: 'q2-1' }] } }).questions[0].questionId, 'q2-1');
assert.equal(normalizeLearningPathQuiz({ data: { questions: [] } }).questions.length, 0);

let calls = 0;
const loader = async () => { calls += 1; return { data: { quiz: { quizId: 'q', questions: [{ questionId: 'q1' }] } } }; };
retryScopedLearningPathQuiz(scope);
await Promise.all([ensureScopedLearningPathQuiz('quiz', scope, loader), ensureScopedLearningPathQuiz('quiz', scope, loader)]);
assert.equal(calls, 1);

let failures = 0;
retryScopedLearningPathQuiz(scope);
await assert.rejects(() => ensureScopedLearningPathQuiz('quiz', scope, async () => { failures += 1; throw new Error('503'); }));
assert.equal(failures, 1);
console.log('learning path quiz render gate: PASS');
