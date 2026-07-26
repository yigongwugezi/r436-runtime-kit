# EduAgent dynamic browser QA

Use the project skill at `.codex/skills/eduagent-browser-qa/SKILL.md`:

```text
Use EduAgent Browser QA Skill to test <feature>.
Check <expected behavior, performance, errors, refresh persistence, or duplicate requests>.
Allow / do not allow <data changes>.
Test only; do not modify code.
```

The default mode is `READ_ONLY`. `SAFE_MUTATION` needs explicit authorization and isolated test data; `DIAGNOSTIC` collects browser evidence; `REGRESSION_AUTHORING` is used only when you explicitly ask to add a stable flow as a Playwright test. Product code is never changed by a QA run unless you explicitly request a test-and-fix run.

Runs save evidence under `frontend/test-results/dynamic-qa/<timestamp>-<slug>/`: charter, result, JSON summary, screenshots, trace, network and console summaries, plus performance data. These files, auth state under `frontend/.qa-auth/`, cookies, tokens, videos, and test results are ignored by Git and must not be committed.

To inspect a live session, run `playwright-cli show`; open `trace.zip` with Playwright Trace Viewer and inspect screenshots from the evidence directory. An expired or unavailable test login is reported as `AUTH_REQUIRED`/`BLOCKED`, never as a product defect.

Results are `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, `BLOCKED`, or `INCONCLUSIVE`; every conclusion links to observed steps and evidence rather than source code or HTTP status alone.
