import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const card = readFileSync(new URL('../src/components/learning/RevisionProposalCard.tsx', import.meta.url), 'utf8');
for (const id of ['adaptive-revision-card', 'adaptive-revision-evidence', 'adaptive-revision-diff', 'adaptive-revision-accept', 'adaptive-revision-reject', 'adaptive-revision-status']) assert.ok(card.includes(id));
assert.ok(card.includes('No actual adjustment needed.') && card.includes('disabled={busy}'));
console.log('adaptive revision card: PASS');
