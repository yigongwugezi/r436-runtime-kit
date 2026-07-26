import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
const handler = source.match(/const handleQuizAnswer = \(questionId: string, value: string\) => \{([\s\S]*?)\n  \};/);

assert.ok(handler, 'quiz answer handler exists');
assert.match(handler[1], /setQuizAnswers\(updated\);/);
assert.match(handler[1], /store\.updateQuizAnswers\(cacheKey, updated\);/);
assert.doesNotMatch(handler[1], /setQuizAnswers\(a =>/);
console.log('lecture quiz answer state: PASS');
