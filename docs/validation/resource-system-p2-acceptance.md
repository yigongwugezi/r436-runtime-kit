# Resource System P2 Acceptance

## Status

`MOSTLY_READY` on `MAF-Refactor` at `f607e14`: backend/API versioning is accepted, while the resource-detail UI still needs an explicit regeneration control and version display.

## Capability matrix

| Resource | Capability | Unavailable behavior |
| --- | --- | --- |
| lecture, quiz, reading, practice | `llm` | disable generation |
| PPT | `ppt` | disable generation |
| image | `image` | disable generation |
| video, animation | `video` | disable generation |
| Manim animation | `manim` | disable generation |
| mindmap | `mindmap` | local deterministic Mermaid fallback remains enabled |
| live search | `search` | return `search_unavailable`; saved resources remain readable |

Capabilities use `available`, `not_configured`, `dependency_missing`, and `unsupported` exactly as returned by the backend. Runtime provider failures use safe retry guidance; authentication failures never request a key from the learner.

## Regeneration

Normal duplicate requests reuse their deterministic resource and workflow task. Explicit `POST /api/resources/{resource_id}/regenerate` requires an `operationId`; it creates v2/v3 successors only after generation succeeds. Each successor copies verified server-side scope, increments `generation_version`, and points `supersedes_resource_id` at its direct predecessor. Locked stages, unproven legacy ownership, and cross-learner/subject scope are rejected before generation or persistence.

## Regression entry points

Run from `backend` with `PYTHONPATH=.`:

```powershell
python -m compileall -q app
python tests/resource_runtime_readiness_test.py
python tests/resource_authorization_scope_test.py
python tests/resource_scope_persistence_test.py
python tests/resource_provider_fallback_test.py
python tests/resource_regeneration_versioning_test.py
python tests/general_resource_generation_test.py
python tests/general_resource_search_test.py
python tests/section_generated_resources_test.py
python tests/chapter_mindmap_resources_test.py
python tests/multimodal_resource_quality_test.py
python tests/focused_lecture_task_test.py
python tests/learning_path_stage_lock_test.py
python tests/resource_interaction_flow_test.py
python tests/workflow_progress_test.py
```

Run frontend checks from `frontend`:

```powershell
node --experimental-strip-types --test tests/resource-capabilities.test.ts
npm run build
```

## Non-blocking P3 limits

- Idempotency is stable in a single process; multi-worker shared locking is not implemented.
- Real-provider smoke tests require a configured key and network access.
- Vite still reports existing large bundle chunk warnings.
- Resource detail still needs an explicit regeneration control and version display; version history remains API-backed.
