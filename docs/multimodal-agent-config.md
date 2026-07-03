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

The frontend keeps the latest image attachment for the active chat session. It reuses that image only when the new message explicitly references the image, for example:

- 这张图 / 这张图片 / 上面这张图 / 刚才那张图
- 图中 / 图片里 / 这道题 / 这页笔记 / 题图 / 错题图
- 继续讲第2题
- 根据这张图生成思维导图
- 根据这张图生成复习卡片
- 根据这张图生成完整学习资源包

Ordinary messages such as `你好`、`帮我生成几道练习题`、`今天学习计划怎么安排`、`解释一下导数` must not automatically attach the last image.

When the frontend detects an explicit reference, it shows a chip such as `正在引用上一张图片`. The user can cancel it; the request then carries `ignore_image_context=true`, and the backend must not reuse the cached image for that message.

New chat sessions clear the frontend image reference. Uploading a new image replaces the old reference. Backend image context is isolated by `session_id`.

## Display Rules

`explain_image_question` uses normal chat text as the main answer. Structured extraction stays behind `查看识别详情`.

User image messages render a 120-200px thumbnail. The thumbnail opens a larger preview modal. If the image cannot load, the UI shows a clear fallback link instead of a broken icon.

Mindmap tasks show Markmap first. OCR and image-understanding details stay collapsed. Markdown fallback remains available if Markmap rendering fails.

Flashcards render as real cards: front first, back folded, math rendered where possible, and extra cards folded after the first six.

Resource bundles hide empty sections, empty arrays, dot-only placeholders, and pending-only shells without content. AI-generated resource and knowledge candidates remain pending until the user explicitly saves or confirms them.

Do not show internal fields such as `type=unknown`, raw payloads, `fallback_rule`, or large JSON in the main chat bubble.

## Math Rendering

The frontend uses the existing Markdown + `remark-math` + `rehype-katex` pipeline. A small normalization pass wraps common bare LaTeX fragments such as `\frac{1}{x}`, `\sqrt{x}`, `\varphi`, and `\begin{cases}...\end{cases}` so they render more readably.

If a formula cannot be normalized, the original text remains visible rather than crashing the page.

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
