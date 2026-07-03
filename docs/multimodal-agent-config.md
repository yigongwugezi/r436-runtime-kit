# Multimodal Agent Configuration

Do not commit real API keys.

## Provider Setup

Recommended Qwen-VL settings:

```env
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VL_MODEL=qwen3-vl-plus
QWEN_IMAGE_ENDPOINT=https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations
```

Keys are read from `DASHSCOPE_API_KEY` or `QWEN_API_KEY`. Missing keys return `provider_not_configured`; the agent must not fake OCR, answers, images, videos, or knowledge-base writes.

## Model Split

Qwen-VL handles image work only:

- image understanding
- OCR-like text extraction
- question, option, formula, and knowledge-point extraction
- uncertainty metadata

The project main LLM handles teaching text:

- question explanation
- wrong-answer analysis wording
- Markmap markdown
- flashcards
- variant questions
- learning-plan/resource-bundle text organization

User-facing teaching answers should come from the main LLM or a small evidence-based fallback. Raw Qwen-VL JSON stays in collapsed details.

## Image Context

The backend chat session keeps the latest successful image context:

- `last_image_input`
- `last_uploaded_file`
- `last_vision_result`
- `last_extracted_questions`
- `last_multimodal_task_context`

The frontend keeps a small image attachment history for the active chat session. It reuses the currently selected image only when the new message explicitly references the image, for example:

- 这张图 / 这张图片 / 上面这张图 / 刚才那张图
- 图中 / 图片里 / 这道题 / 这页笔记 / 题图 / 错题图
- 继续讲第2题
- 根据这张图生成思维导图
- 根据这张图生成复习卡片
- 根据这张图生成完整学习资源包

Ordinary messages such as `你好`、`帮我生成几道练习题`、`今天学习计划怎么安排`、`解释一下导数` must not automatically attach the last image.

When the frontend detects an explicit reference, it shows an image reference chip with a thumbnail. If the current session has multiple uploaded images, the user can choose which thumbnail is the active reference. The user can also cancel it; the request then carries `ignore_image_context=true`, and the backend must not reuse the cached image for that message.

New chat sessions clear the frontend image reference history. Uploading a new image adds it to the history and selects it by default. Backend image context is isolated by `session_id`.

## Local Image Preview

In local development the backend runs on `http://127.0.0.1:8000`. Vite must proxy `/api` to that port. Uploaded image URLs are relative paths such as `/api/multimodal/file/<file_id>`; they should not hardcode `8001` or any absolute local host.

The chat input chip lives directly above the textarea. It shows the selected image thumbnail, `正在引用图片`, optional `更换`, and a clear `取消引用` button. After cancellation the current request sends `ignore_image_context=true`.

## Display Rules

`explain_image_question` uses normal chat text as the main answer. Structured extraction stays behind `查看识别详情`.

The stable main text fields are `display_text`, `teaching_text`, or `chat_text`; product chat returns those before any fallback status sentence.

`查看识别详情` accepts question fields named `question_text`, `stem`, `question`, `text`, `content`, or `title`. If a question has no readable stem, show `题干识别不完整` and list it in review metadata instead of rendering an empty number.

User image messages render a 120-200px thumbnail. The thumbnail opens a larger preview modal. If the image cannot load, the UI shows a clear fallback link instead of a broken icon.

Mindmap tasks show Markmap first. OCR and image-understanding details stay collapsed. Markdown fallback remains available if Markmap rendering fails.

Mindmap generation should use the full cached `last_vision_result`, including `detected_text`, extracted questions, answers, formulas, and knowledge points. If the main LLM returns a sparse map, the backend falls back to a local evidence-based map rather than showing two or three nodes.

Flashcards render as real cards: front first, back folded, math rendered where possible, and extra cards folded after the first six. Multi-question images should produce at least six useful study cards when enough evidence exists. Card fronts should be review questions, and backs should be explanatory answers rather than OCR fragments.

Resource bundles start with a short explanation of what the bundle is, what saving does, and why knowledge candidates stay pending. Empty sections, empty arrays, dot-only placeholders, and pending-only shells without content are hidden. AI-generated resource and knowledge candidates remain pending until the user explicitly saves or confirms them.

Do not show internal fields such as `type=unknown`, raw payloads, `fallback_rule`, or large JSON in the main chat bubble.

## Math Rendering

The frontend uses the existing Markdown + `remark-math` + `rehype-katex` pipeline. A small normalization pass wraps common bare LaTeX fragments such as `\frac{1}{x}`, `\sqrt{x}`, `\varphi`, and `\begin{cases}...\end{cases}` so they render more readably.

KaTeX is configured not to throw on parse errors. If a formula cannot be normalized, the original text remains visible rather than crashing the page or showing a red error block.

## Manual Review

`needs_manual_review=true` is only for real uncertainty, such as missing OCR, truncated stems, incomplete options, unclear formulas, or low confidence.

When true, return:

- `review_reasons`
- `uncertain_question_indices`
- `uncertain_fields`
- `uncertain_spans` when available
- `review_level`: `low`, `medium`, or `high`
- `can_continue`: whether the user can keep using the current result

The frontend should say `以下内容可能需要你确认`, list concrete reasons, translate internal paths like `cards[11].back` into human text, and avoid fake confirmation flows.

## Trace

`workflow_trace` may expose:

- `reused_image_context`
- `image_context_source`
- `vision_extract_by_qwen_vl`
- `vision_context_reused`
- `teaching_generation_by_main_llm`
- `mindmap_generation_by_main_llm`
- `flashcard_generation_by_main_llm`
- `variant_generation_by_main_llm`

Never include API keys in traces, logs, docs, or tests.

## Smoke

Mock acceptance smoke:

```powershell
cd C:\Users\20825\Documents\Codex\2026-06-07\seedance-ai-claude-code-ai-ai\backend
$env:PYTHONIOENCODING="utf-8"
.venv310\Scripts\python.exe scripts\smoke_multimodal_image_acceptance.py
```

The script does not call real providers. It checks that preview URLs do not use `8001`, explanation has `display_text`, internal placeholders do not leak, details do not become empty question numbers, mindmap labels stay short, flashcards have at least six cards, resource bundles explain their purpose and drop empty sections, and manual review has actionable reasons.
