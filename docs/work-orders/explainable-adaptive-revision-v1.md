# Explainable adaptive revision v1 work order

## Read-only audit (2026-07-26)

### Existing chain and reusable components

`POST /api/learning-path/tasks/{taskId}/quiz/submit` persists an `AttemptModel`, writes the canonical `learning_events.quiz_result` record (unique per attempt), persists quiz weak points to the profile snapshot, and creates the persisted, attempt-idempotent `assessment_processing` workflow. That workflow already owns the diagnosis call and routes through `DiagnosisAgent`, `PlannerAgent`, `ConversationStore.set_pending_revision`, `LearningPathModel.pending_revision`, and the existing `RevisionProposalCard`.

Existing path safety is also reusable: scoped ownership checks in the assessment and revision endpoints, `CurrentLearningPathModel`, `_preserve_task_progress`, and pending revisions that do not replace the canonical path until acceptance.

### Gaps found

The old direct post-submit trigger deliberately returns before running. The workflow invokes the assessment loop but omits the attempt's path/stage/task, subject, event id, and weak-point evidence. Planner output can be zero-diff or LLM-dependent, so a low fresh task-quiz attempt has no deterministic nonzero proposal. Pending revisions currently use a timestamp id, do not retain a decision record, and accept/reject are not replay-idempotent. The card only shows generic stage/task lists and lacks evidence/diff/status test hooks.

## v1 contract

Only a fresh, failed path-task quiz attempt is in scope. The trigger key is `learnerId|sessionId|pathId|quizAttemptId|adaptive_review_v1`; it contains no timestamp. A qualifying revision adds exactly one stable review task to the same stage/day as the failed quiz, leaves every existing task (especially completed tasks) unchanged, and never silently applies.

Evidence carries only learner/session/subject/path/stage/task/attempt ids, quiz score, pass threshold, attempt index, best score, weak knowledge points, event timestamp/type, and trigger reason. The explainability payload includes summary, reason, evidence, expected outcome, affected ids, added/removed tasks, duration delta, risk flags, generator, and trigger event id.

Lifecycle: `pending` (represented by the existing `ready_for_review`) -> `accepted` -> `applied`, or `rejected`; a competing later proposal is `superseded`, and invalid construction is `failed`. One active proposal exists per attempt. Replayed submit/accept/reject are no-ops with their original result. A zero diff is retained as an informational result with no actions.

## State machine and safety boundaries

```
quiz attempt recorded -> learning evidence -> diagnosis updated
  -> revision generation started -> generated -> pending
  -> accepted -> applied
  -> rejected
```

All workflow entries contain stage/status/duration/service/input/output, fallback flag and safe error code; no credentials or prompts are recorded. The revision only targets the canonical scoped path; subject/session/path and learner ownership are checked before read, accept, or reject. No completed task is changed, removed, or regressed. LLM failure uses the deterministic review-task builder; it never invents a fixed task id, fixed knowledge point, or fixed score.

## Implementation and acceptance

1. Add a small deterministic adaptive-revision builder used by the existing assessment workflow after diagnosis, backed by the existing event and pending-revision persistence.
2. Extend pending revision persistence/endpoints for idempotent decisions, explainability, and revision history.
3. Extend the existing revision card only; do not add a page.
4. Add focused backend and frontend source checks for low/pass/replay/scope, completed-task preservation, fallback, lifecycle/trace, and UI test ids.
5. Run isolated `SAFE_MUTATION` browser QA for accept and reject plus adjacent quiz-retake, path-performance, mindmap, and video-fallback checks. Evidence will be saved outside source control under `frontend/test-results/`.

## Result

Implemented the deterministic v1 review insertion in the existing
`assessment_processing` flow. The proposal uses the persisted quiz result and
answer records, has a stable per-attempt idempotency key, is stored in the
existing pending-revision field, and applies only after the learner accepts.
The existing card now exposes evidence, change details, status, and disabled
actions for an actual zero diff.

Focused backend and frontend checks pass. Isolated browser QA passed in fresh
accept and reject sandboxes, and the adjacent path-performance, mindmap,
video-fallback, and quiz-retake scenarios passed. Evidence lives in ignored
`frontend/test-results/dynamic-qa/2026-07-26T15-14-46-813Z-adaptive-revision/`
and `frontend/test-results/dynamic-qa/2026-07-26T15-15-01-092Z-adaptive-revision-reject/`.
