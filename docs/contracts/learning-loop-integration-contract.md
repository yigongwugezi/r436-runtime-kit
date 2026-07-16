# Learning loop integration contract

This document defines public integration boundaries only.  It does not assign
or implement any teammate's business logic.

## Quality status

New public values are limited to `passed`, `needs_review`, `blocked`, and
`provider_unavailable`.

Older values remain readable through the compatibility layer only:

| Legacy value | Public value |
| --- | --- |
| `warning`, `repaired`, `fallback`, `fallback_passed` | `passed` |
| `review_required` | `needs_review` |
| `failed` | `blocked` |

`blocked` and `provider_unavailable` must never be silently represented as a
successful result.

## Workflow names

The only workflow names for the guided-planning team are
`learning_path_planning` and `path_revision`.

The assessment/diagnosis team owns `assessment_processing` and
`diagnosis_refresh`.  Callers must use these names unchanged in task keys,
SSE events, recovery records, and frontend API types.

## Shared DTO scope

Every cross-module DTO carries `learner_id`, `subject_id`, and `session_id`.
It also carries the relevant optional scope identifiers from `path_id`,
`stage_id`, `chapter_id`, `section_id`, `attempt_id`, and
`diagnosis_version`.  The receiver must not infer a missing scope from a
different learner, subject, or session.

The assessment/diagnosis team defines the implementations of:

- `DiagnosisSnapshotDTO`
- `DiagnosisEvidenceDTO`
- `PersonalizationContextDTO`
- `QuizResultEventDTO`

The guided-planning team defines the implementations of:

- `LearningPathPlanningDraftDTO`
- `PathRevisionDTO`
- `PathDiffDTO`
- `PathRevisionDecisionDTO`

Explicit learner facts override lower-confidence inferred facts.  Disabled,
locked, and deleted facts remain excluded from downstream DTOs.

## Shared-file integration rule

Business logic stays in the owning module.  Changes to the following shared
surfaces are separate, small commits with a matching contract test:

- `backend/app/routers/workflows.py`
- FastAPI router registration
- common database model registration
- common repository entry points
- frontend common API types
- `backend/app/routers/product.py`
- `WorkflowTaskManager`

No shared surface may introduce a second task manager, alternate scope key,
or bypass of the existing ownership checks.

## P6 task contract

Long-running workflows publish task identity, status, elapsed time, progress,
result reference, and terminal error state through the existing task status
and SSE endpoints.  The task key includes the workflow name and all input
scope fields that alter backend work.  Reconnect, retry, cancellation, and
page-refresh recovery must reuse that task identity; they must not create a
second runner.
