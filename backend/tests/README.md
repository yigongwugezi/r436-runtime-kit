# Runtime Kit Conversation Tests

This folder contains lightweight conversation tests for the learning-profile dialogue flow.

## Run all conversation tests

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File backend\tests\run_conversation_tests.ps1
```

Or run the two scripts directly:

```powershell
backend\.venv\Scripts\python.exe backend\tests\conversation_eval.py
backend\.venv\Scripts\python.exe backend\tests\conversation_regression.py
```

## Add a new dialogue case

Add a case to `conversation_cases.json`.

Common checks:

- `intent`: expected intent for a user turn.
- `reply_contains`: text that must appear in the assistant reply.
- `reply_not_contains`: text that must not appear in the assistant reply.
- `expect_facts`: exact expected profile fields after the dialogue.
- `expect_fact_contains`: partial expected profile field content.
- `expect_missing_facts`: profile fields that must remain empty.
- `expect_ready_to_plan`: whether the dialogue is enough to generate a learning plan.

When a user finds a weird phrase, add it here first. The test should fail before the fix and pass after the fix.
