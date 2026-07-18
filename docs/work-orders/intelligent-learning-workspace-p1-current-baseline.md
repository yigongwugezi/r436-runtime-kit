# Intelligent Learning Workspace P1: Current Baseline

The legacy `intelligent-learning-workspace-p1.md` is retained unchanged because it is not UTF-8 and its baseline predates the current branch. Profile V2 P2-P5, workflow recovery, resource capabilities, and resource versioning are already implemented and out of scope here.

## First atomic task

Make the persistent right-side `ChatPanel` render the safe status and `user_message` already supplied in `ChatMessage.multimodalResult`.

- Input: existing `/api/chat/send` and stream-completion `multimodal_result`.
- Output: concise safe status in the panel; never a key, provider URL, or upstream response.
- Modules: `frontend/src/components/chat/ChatPanel.tsx` plus focused UI coverage.
- Exclusions: no migration, Agent/router redesign, Profile V2 change, or automatic learning-plan trigger.
- Acceptance: provider unavailability is explicit, Mermaid remains renderable, ordinary chat is unchanged, and `npm run build` passes.
