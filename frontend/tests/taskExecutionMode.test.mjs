import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const resolver = readFileSync(new URL('../src/utils/taskExecutionMode.ts', import.meta.url), 'utf8');
const page = readFileSync(new URL('../src/pages/LecturePage.tsx', import.meta.url), 'utf8');
const videos = readFileSync(new URL('../src/api/videoRecommendations.ts', import.meta.url), 'utf8');
assert.match(resolver, /\['video', 'watch_video'\].*return 'video'/);
assert.match(page, /if \(executionMode === 'video' && !videoLectureFallback\) return;/);
assert.match(videos, /resourceTypes: \['video'\]/);
assert.match(page, /暂未找到与当前任务高度相关的视频资源/);
assert.match(page, /setVideoLectureFallback\(true\)/);
assert.match(page, /当前使用图文讲解替代视频学习/);
console.log('task execution mode: PASS');
