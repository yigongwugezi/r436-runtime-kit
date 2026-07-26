import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const hook = readFileSync(new URL('../src/hooks/useProfile.ts', import.meta.url), 'utf8');
const api = readFileSync(new URL('../src/api/profile.ts', import.meta.url), 'utf8');
const page = readFileSync(new URL('../src/pages/ProfilePage.tsx', import.meta.url), 'utf8');

assert.match(hook, /const profileRequests = new Map/);
assert.match(api, /subjectId: string/);
assert.match(hook, /function readProfile\(sessionId: string, subjectId: string\)/);
assert.match(hook, /profileApi\.getProfile\(\{ sessionId, subjectId \}\)/);
assert.match(hook, /if \(!canLoadCanonicalData\(canonicalStatus, currentSessionId\) \|\| !currentSubjectId\)/);
assert.match(hook, /profileRequests\.get\(requestKey\)/);
assert.match(hook, /currentCanonical\.subjectId !== currentSubjectId/);
assert.match(hook, /finally \{\s*if \(generation === fetchGenRef\.current\) \{ setLoading\(false\)/);
assert.match(page, /empty \? '画像信息暂不完整'/);
assert.doesNotMatch(hook, /const store = useProfileStore\(\)/);
console.log('profile loading state: PASS');
