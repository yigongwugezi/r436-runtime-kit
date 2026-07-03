# Multimodal Agent Configuration

Do not commit real API keys.

## Provider Setup

Recommended Qwen-VL settings:

```env
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VL_MODEL=qwen3-vl-plus
QWEN_IMAGE_ENDPOINT=https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations
```

Keys are read from `DASHSCOPE_API_KEY` or `QWEN_API_KEY`. Missing keys return `provider_not_configured`; the agent must not fake OCR, answers, images, or videos.

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

If the main LLM fails, the backend returns a small local result from extracted evidence and adds a warning. It must not expose raw JSON as the user-facing answer.

## Image Context

The chat session keeps the latest image context:

- `last_image_input`
- `last_uploaded_file`
- `last_vision_result`
- `last_extracted_questions`
- `last_multimodal_task_context`

The frontend also keeps the latest upload attachment for the active chat session and reuses it for phrases such as:

- 这张图
- 上面这张图
- 刚才那张图
- 图中 / 图片里
- 这道题 / 这页笔记
- 继续讲第2题
- 根据这张图生成思维导图
- 根据这张图生成复习卡片
- 根据这张图生成完整学习资源包

New chat sessions clear the frontend image reference. Uploading a new image replaces the old reference.

`workflow_trace` exposes:

- `reused_image_context`
- `image_context_source`
- `vision_extract_by_qwen_vl`
- `vision_context_reused`
- `teaching_generation_by_main_llm`
- `mindmap_generation_by_main_llm`
- `flashcard_generation_by_main_llm`
- `variant_generation_by_main_llm`

## Display Rules

`explain_image_question` uses normal chat text as the main answer. Structured extraction stays behind "查看识别详情".

Do not show internal fields such as `type=unknown`, raw payloads, or large JSON in the main chat bubble. Unknown image type should be hidden or shown as a natural Chinese note.

## Manual Review

`needs_manual_review=true` is only for real uncertainty, such as missing OCR, truncated stems, incomplete options, unclear formulas, or low confidence.

When true, return:

- `review_reasons`
- `uncertain_question_indices`
- `uncertain_fields`
- `uncertain_spans` when available

Partial uncertainty should not hide the usable parts of the result.

## Resource Candidates

AI-generated resources and knowledge candidates stay pending until the user explicitly saves or confirms them. The formal knowledge base is not written automatically.
