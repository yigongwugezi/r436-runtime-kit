---
name: eduagent-browser-qa
description: Run evidence-backed, natural-language browser QA for EduAgent: page/function checks, console and network diagnostics, performance, visual layout, refresh persistence, duplicate requests, and explicitly requested Playwright regression authoring.
---

# EduAgent Browser QA

Use this skill when asked to test, verify, inspect, diagnose, regression-test, or debug an EduAgent web flow. Use the installed `playwright-cli` skill and an isolated named session `eduagent-qa-<timestamp>`.

## Safety first

Before opening a browser, write `charter.md` in `frontend/test-results/dynamic-qa/<timestamp>-<slug>/` with: original request; goal; exclusions; mode; data-write/task-completion/resource-generation/external-LLM permissions; entry URL; prerequisites; steps; expected result; thresholds; watched APIs/console events; evidence; recovery; PASS/FAIL/BLOCKED rules.

Default to `READ_ONLY`: do not mutate data, complete tasks, generate resources, regenerate paths, delete resources, change code, commit, or push. If a flow needs a mutation, use `SAFE_MUTATION` only with explicit permission, test data or an isolated database/account, an idempotency key where supported, and a cleanup/isolation plan. Otherwise return `BLOCKED`; never touch formal production state. Never log cookies, authorization headers, or tokens.

Choose one data mode in every charter. `EXISTING_LOCAL_DATA` is read-only and is only for an explicitly requested existing local state. `ISOLATED_QA_SANDBOX` is the default for mutations, retries, regression flows, and when no safe existing state exists: run `npm run qa:browser:prepare`, point the backend's `DATABASE_URL` at the emitted `.qa/runtime/.../qa.db`, and use its deterministic IDs. A sandbox failure—not missing manual preparation—is the only reason to report `BLOCKED` for test data.

For `ISOLATED_QA_SANDBOX`, prepare, authenticate, read `seed-metadata.json`, then invoke `frontend/tests/e2e/helpers/bootstrapQaSubject.mjs`. It discovers the seeded subject through the authenticated API, ensures its canonical session, applies the verified subject-store persistence contract, reloads, and verifies the exact path before the charter. Do not hand-click setup or hard-code fixture IDs outside metadata.

Load `.qa/runtime/.../auth-runtime.json` only at runtime and use `authenticateQaUser.mjs` to call the real login contract, save ignored storageState under `frontend/.qa-auth/`, reload it in a fresh context, and verify `/api/auth/me` before bootstrap. Never print credentials, tokens, cookies, or headers. Retry a stale state through one fresh login; then report `AUTH_ERROR`.

Modes:
- `READ_ONLY`: navigation, rendering, refresh, existing-state checks, performance, console/network inspection only.
- `SAFE_MUTATION`: explicitly authorized, isolated test-data writes; record request/response status and verify persistence after reload.
- `DIAGNOSTIC`: collect console/page errors, failed/4xx/5xx requests, duplicate requests, loading, performance and layout evidence.
- `REGRESSION_AUTHORING`: only when the user explicitly asks to make a stable flow a Playwright test. First perform the live exploration; then add the smallest independent test using role/label/testid locators, isolated data, and mocks for external LLM/search where possible.

## Plan, then operate

1. Read the relevant frontend route/page/API client and backend router/service without editing. Identify the canonical route, preconditions, safe visible text/role/label/testid locators, watched endpoints, and mutation risk.
2. Reuse a healthy project service on `127.0.0.1:5173` and `:8000`; do not kill an unknown process. If absent, start only isolated child processes, without backend `--reload`, wait for `/api/health` rather than sleeping, and close only those children afterwards.
3. Reuse an existing test login fixture or dedicated test account. Storage state belongs under `frontend/.qa-auth/` and is never committed. If authentication is unavailable or expired, report `AUTH_REQUIRED`/`BLOCKED`, not a product failure.
4. Start `playwright-cli -s=<session> open <url>`, `tracing-start`, and snapshot. Locate via the accessibility snapshot; after every navigation or state change snapshot again. Do not rely on stale refs or a source-only claim.
5. Save full-page and relevant-region screenshots, trace, network summary, console summary, performance JSON, `summary.json`, and `result.md` in the evidence directory. Record method, path (redacted query), status, duration, initiator/step and count.
6. Close the named session and only processes started by this run.

## Required diagnostics

For every live run check console errors/warnings, page errors, request failures, response status >=400, blocked dialogs, persistent loading, and duplicate watched requests. Classify separately as `PRODUCT_ERROR`, `TEST_INFRA_ERROR`, `AUTH_ERROR`, `EXTERNAL_SERVICE_ERROR`, `EXPECTED_DEGRADED`, `PERFORMANCE_WARNING`, `DUPLICATE_REQUEST`, or `VISUAL_LAYOUT_ERROR`.

When slow/laggy is requested collect navigation, DOMContentLoaded, load, first main-content visibility, critical request durations, workflow duration, loading duration, request count and duplicates. Local reference warnings: GET >500ms, mutation >1000ms, main persisted content >1s; loading >10s with no progress is `FAIL` or `BLOCKED`. One run is an observation, not a regression conclusion.

For visual requests, prove visibility with bounding boxes, viewport/intersection, overlays, overflow, clickable controls and screenshots. For mind maps additionally require a sensible graph/container box, content box not near zero, >1 node, nodes not all on one horizontal line, and visible fit/resize result. Failed checks are `VISUAL_LAYOUT_ERROR`.

## Results

Use only `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, `BLOCKED`, or `INCONCLUSIVE`. Each conclusion must cite step, expected vs actual, request/status/duration where applicable, evidence filenames, and error classification. A successful HTTP response, existing element, or passing script alone is not a UI pass.

If a product issue is found, preserve evidence and report the minimal reproduction, likely frontend/backend area, risk and smallest proposed fix; do not change code unless the user explicitly authorizes testing and fixing. If regression authoring was requested, generate the test only after a stable live path exists; do not commit unless explicitly asked.

## User invocation

`Use EduAgent Browser QA Skill to test <feature>. Check <expectations>. Allow/do not allow <data writes>. Test only; do not modify code.`

Examples: “test mind-map rendering, layout, speed, console and failed requests; do not generate anything” and “test quiz retake with isolated test data, verify submit de-duplication and refresh persistence; do not fix code.”
