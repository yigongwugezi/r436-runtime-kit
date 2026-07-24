# Core flow stability audit — 2026-07-24

Evidence: `frontend/src/{hooks/useLearningPath.ts,pages/{LearningPathPage,LecturePage}.tsx}`, `frontend/src/api/{client,learningPath,assessment,videoRecommendations}.ts`, `backend/app/routers/{assessment,product,rag}.py`, `backend/app/services/workflow_tasks.py`, and the focused tests listed below.  No production SQLite database was opened or changed.

## Request budget

| Flow | Canonical scope | First-load/read budget | Mutation budget | Current enforcement |
| --- | --- | --- | --- | --- |
| Login / subject | learner, session, subject | `auth/me`, subjects, session resolution: 1 each | none | router/session ownership guards |
| Persisted path | learner, session, subject, path | canonical path: 1; profile: 1; drafts secondary | none | request id + `AbortController`; stale response ignored |
| Read document | learner, session, subject, path, stage, day, task | exact path/task state: 1; lecture ensure: 1 | complete: 1 | canonical resolver; workflow recovery and terminal stopping |
| Quiz | learner, session, subject, path, stage, day, task | ensure: 1 | submit: 1; retry creates a new client attempt/key | frontend in-flight lock; backend idempotency conflict/replay |
| Video / fallback | learner, session, subject, path, stage, day, task | task state: 1; fallback ensure: 1 | delivery mode, opened evidence, complete: 1 each | delivery-mode lock; canonical completion and resource reuse |

## Flow findings

### A. Login and subject entry

Entry is the protected frontend router. The canonical scope is learner/session/subject. There is no observed polling or LLM invocation in this entry path; auth/session validation is server-side. No legacy navigation route was found in the active router.

### B. Persisted learning path

`useLearningPath` is the sole path hook used by the path and task workspaces. It requests the canonical persisted path, cancels superseded GETs, ignores stale request ids, and now always clears the primary loader for the current settled request. `LearningPathPage` loads planning drafts independently, so draft failure cannot hold the primary path hostage. Known limitation: no global query cache; request identity protection is local to the hook instance.

### C. read_doc lecture

`LecturePage` resolves its task from the persisted path using session/subject/path/stage/day/task, then uses `ensureLecture`. Workflow loops are scoped and stop on terminal states; completion uses the formal task-complete API and refetches the exact path before navigation. Optional lecture/RAG-related failures render a local degraded state rather than completing a fabricated task.

### D. Quiz

The router grades and persists an attempt synchronously, retains same-key/same-answer replay and same-key/different-answer 409 behavior, and launches only one attempt-scoped `assessment_processing` workflow. The former untracked post-submit runner and second diagnosis-refresh task both return immediately. `LecturePage` now assigns a fresh `clientAttemptId` and idempotency key on initial answer and retake; retries reuse the key, while a synchronous ref lock prevents double-click/StrictMode duplicate submits. Latest score, best score, current-pass and ever-passed are returned by the backend; passed-path completion is monotonic.

### E. Video and fallback lecture

Video uses canonical day scope rather than parsing a task id. Delivery mode is persisted, guarded against duplicate clicks, and fallback lecture ensure rejects ordinary lecture generation for video tasks. Existing fallback resources are reused. Fallback completion records opened evidence and the fallback resource id on the original video task, refetches the canonical path, then navigates only after confirmation. Workflow polling stops for terminal states.

## Optional capability and hot-path conclusions

RAG registration is guarded by configuration; unavailable providers return local capability/error states instead of blocking core task completion. DeepTutor calls have existing fallback paths. Mind-map tasks return a stable local failure/empty state instead of blocking lecture completion. `assessment_processing` is asynchronous and deduplicated per attempt. No index migration was added: current focused tests use temporary SQLite databases, and no evidence in this audit supports a new production index.

## Legacy isolation and regression tests

The active router enters the unified learning workspace. `legacy=1` is excluded from task-route behavior. The prior `taskExecutionMode.test.mjs` source-text gate was replaced with direct resolver behavior assertions. `learning_task_completion_test.py` already uses the official current-path resolver contract and temporary SQLite.

## Focused validation

- Frontend: path completion, pending revision scope, canonical task scope, workflow recovery, execution mode, video fallback delivery mode, and production build.
- Backend: assessment idempotency, canonical task completion, and video fallback completion tests (temporary SQLite only).
- Browser smoke: not run; existing browser automation was not invoked in this pass.

Status: `IMPLEMENTATION_COMPLETE_BROWSER_SMOKE_REQUIRED` once focused backend validation completes.
