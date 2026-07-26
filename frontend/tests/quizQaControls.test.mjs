import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const page = await readFile(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
for (const id of ['quiz-question-${q.questionId}', 'quiz-option-${q.questionId}-${letter}', 'quiz-submit', 'quiz-retake', 'quiz-score', 'quiz-result']) assert.ok(page.includes(id));
assert.ok(!page.includes('correctAnswer"'));
console.log('quiz QA controls: PASS');
