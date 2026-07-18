# Competition Demo V1 acceptance

## Scope

- Theme: Higher Mathematics — Derivative Fundamentals.
- Data: deterministic temporary SQLite learner, subject, session, path, quiz, and resources; no real account or password.
- Providers: mock LLM/Search in backend checks. If a multimodal provider is unavailable, show its existing safe unavailable state and continue with lecture or mind-map fallback.

## Demo steps and expected results

1. Sign in, select/create the calculus subject, and enter its session.
2. State a learning goal, then explicitly request a plan. A persisted two-stage path appears: Derivative Fundamentals is current; Derivative Applications is locked.
3. Open the focused lecture with its `sessionId`, `subjectId`, `pathId`, `stageId`, `taskId`, and `returnTo`. The lecture and ChatPanel are non-empty.
4. Mark the lecture complete. The first stage remains current because its required quiz is incomplete.
5. Submit the focused quiz. Score and explanation appear; the linked path task completes; the next stage becomes current; Analytics reads the updated `nextTask` from the backend.
6. Reload the path and analytics pages. The persisted stage state remains current/completed as above.
7. Open Resource Library, read the lecture or mind-map, bookmark/update its study state, then explicitly regenerate it. The new version links to the old resource; the original remains readable.
8. Attempt a locked-stage URL or use another learner. The request is rejected with the existing explicit 403 behavior.

## Verification and fallback

- Backend: `competition_demo_v1_e2e_test.py`, assessment/path, analytics, resource, and authorization regressions.
- Browser: `npm run test:e2e` runs the real Edge/Vite fake-server journeys, including path route-context persistence and resource capability fallbacks.
- Fallback: if browser automation cannot start Edge, run the backend deterministic demo test and present the same seeded flow through the local UI; no real network is needed.
- Non-blocking: Vite reports existing chunk-size/dynamic-import warnings. They do not prevent a production build.
- Baseline commit: `a603b2d`; run `git rev-parse HEAD` when recording the frozen release commit.

## Automation status (MOSTLY_READY)

- `compileall`, the deterministic Competition Demo and assessment-to-path checks, focused lecture, path lock/runtime, assessment, analytics, resource authorization/versioning, and deterministic search regressions pass with fake providers and no external network.
- Four Edge journeys pass: browser smoke, general resource generation, learning-path compatibility, and unavailable-Manim capability handling. The production build passes; existing chunk warnings are non-blocking.
- `online-resource-search` lacks reliable browser automation evidence only: the native Edge CDP harness can observe but cannot safely pause a workflow-start request to bind the application-created session. This is a `TEST_HARNESS_GAP`, not a confirmed production bug; validate this UI manually next.
- Not covered here: real search/DeepSeek/PPT/video providers, dynamic replanning, or Agent call-path changes.
