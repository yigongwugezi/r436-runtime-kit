import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const hook = readFileSync(new URL('../src/hooks/useProfile.ts', import.meta.url), 'utf8');
const page = readFileSync(new URL('../src/pages/ProfilePage.tsx', import.meta.url), 'utf8');

assert.match(hook, /const profileRequests = new Map/);
assert.match(hook, /if \(!canLoadCanonicalData\(canonicalStatus, currentSessionId\)\)/);
assert.match(hook, /profileRequests\.get\(sessionId\)/);
assert.match(hook, /generation !== fetchGenRef\.current \|\| useChatStore\.getState\(\)\.dataSessionId !== currentSessionId/);
assert.match(hook, /finally \{\s*if \(generation === fetchGenRef\.current\) \{ setLoading\(false\)/);
assert.match(page, /empty \? '画像信息暂不完整'/);
assert.doesNotMatch(hook, /const store = useProfileStore\(\)/);
console.log('profile loading state: PASS');
