import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/LearningPathPage.tsx', import.meta.url), 'utf8');
const card = readFileSync(new URL('../src/components/learning/RevisionProposalCard.tsx', import.meta.url), 'utf8');

assert.match(page, /<RevisionProposalCard sessionId=\{sessionId\} subjectId=\{subject\.subject_id\} pathId=\{path\.id\} \/>/);
assert.match(card, /getPendingRevision\(sessionId, subjectId, pathId\)/);
assert.match(card, /acceptPendingRevision\(sessionId, subjectId, pathId, proposal\.revision_id\)/);
assert.doesNotMatch(card, /path_session_/);
console.log('pending revision canonical path scope: PASS');
