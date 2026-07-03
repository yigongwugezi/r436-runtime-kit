# Multimodal Agent Configuration

This document lists the environment variables used by `MultimodalAgent`.
Do not commit real API keys.

## Qwen-VL

Used for image understanding, OCR-like extraction, image-to-mindmap, image-to-flashcards, and image-question explanation.

Environment variables:

- `DASHSCOPE_API_KEY`: preferred API key.
- `QWEN_API_KEY`: fallback API key.
- `QWEN_BASE_URL`: OpenAI-compatible base URL. Defaults to `https://dashscope.aliyuncs.com/compatible-mode/v1`.
- `QWEN_VL_MODEL`: vision model name. Defaults to `qwen-vl-plus`.
- `QWEN_TIMEOUT`: optional request timeout in seconds. Defaults to `60`.

Example:

```env
DASHSCOPE_API_KEY=replace-with-your-key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VL_MODEL=qwen-vl-plus
```

When no key is configured, the provider returns `provider_not_configured`. It does not fabricate OCR text, question text, or image summaries.

## Qwen-Image

Used for image generation, concept cards, and teaching diagrams.

Environment variables:

- `DASHSCOPE_API_KEY`: preferred API key.
- `QWEN_API_KEY`: fallback API key.
- `QWEN_IMAGE_MODEL`: image generation model. Defaults to `qwen-image`.
- `QWEN_IMAGE_ENDPOINT`: full image generation endpoint.
- `QWEN_IMAGE_BASE_URL`: base URL used when `QWEN_IMAGE_ENDPOINT` is not set.
- `QWEN_BASE_URL`: fallback base URL.
- `QWEN_TIMEOUT`: optional request timeout in seconds. Defaults to `60`.

Example:

```env
DASHSCOPE_API_KEY=replace-with-your-key
QWEN_IMAGE_MODEL=qwen-image
QWEN_IMAGE_ENDPOINT=https://dashscope.aliyuncs.com/compatible-mode/v1/images/generations
```

When unconfigured, the provider returns `provider_not_configured`. It does not return fake image URLs.

## Wan Video

Used for video generation and micro-lesson video tasks. The agent can still create a text script and storyboard without the Wan video API.

Environment variables:

- `DASHSCOPE_API_KEY`: fallback API key.
- `WAN_API_KEY`: preferred Wan-specific API key when available.
- `WAN_VIDEO_MODEL`: video model name. Defaults to `wanx2.1-t2v-turbo`.
- `WAN_VIDEO_ENDPOINT`: video task creation endpoint.
- `WAN_TIMEOUT`: optional request timeout in seconds. Defaults to `60`.

Example:

```env
WAN_API_KEY=replace-with-your-key
WAN_VIDEO_MODEL=wanx2.1-t2v-turbo
WAN_VIDEO_ENDPOINT=https://example.com/video/tasks
```

When unconfigured, the provider returns `script_ready_provider_not_configured` with a local micro-lesson script and storyboard. It does not return fake video URLs.

## Supported Image Inputs

`MultimodalAgent` accepts:

- `image_url`
- `image_base64`, including raw base64 or `data:image/...;base64,...`
- uploaded images saved through `POST /api/multimodal/upload`

Uploads are stored under `backend/uploads/multimodal/<session_id>/<uuid>.<ext>`.
Allowed image types are PNG, JPG, JPEG, and WEBP. The current single-image limit is 10 MB.

## Frontend

The chat page can upload an image, preview it, send it with the message, and render structured multimodal results:

- vision summary and recognized text
- image-to-mindmap output through Markmap
- flashcards
- generated image URLs returned by the provider
- video script and storyboard text

Provider errors such as `provider_not_configured` and `needs_manual_review` are shown as explicit states instead of fake successful results.

## Image AI Learning Workflow

The image workflow keeps one execution path: upload or pass an image, classify the image task, call Qwen-VL once with a task-aware JSON prompt, normalize the result, and return a structured `multimodal_result`.

Supported task types:

- `image_understanding`
- `explain_image_question`
- `image_wrong_question_analysis`
- `image_note_summary`
- `image_to_mindmap`
- `image_to_flashcards`
- `image_to_learning_plan`
- `image_to_variant_questions`
- `image_to_resource_bundle`

Returned task results are always wrapped by:

```json
{
  "agent": "MultimodalAgent",
  "status": "success | partial_success | needs_manual_review | failed | provider_not_configured",
  "task_type": "image_understanding",
  "tool": "QwenVisionProvider",
  "provider": "qwen_vl",
  "result": {},
  "warnings": [],
  "trace": {},
  "agent_step": {},
  "workflow_trace": {}
}
```

Task result shapes:

- `image_understanding`: `image_type`, `subject`, `detected_text`, `summary`, `possible_knowledge_points`, `confidence`, `needs_manual_review`.
- `explain_image_question`: `question_text`, `question_type`, `subject`, `knowledge_points`, `answer`, `explanation_steps`, `key_method`, `common_mistakes`, `confidence`, `needs_manual_review`, `evidence_from_image`.
- `image_wrong_question_analysis`: `question_text`, `correct_answer`, `student_answer`, `mistake_type`, `mistake_reason`, `weak_knowledge_points`, `remediation_plan`, `similar_practice_suggestions`, `confidence`, `needs_manual_review`.
- `image_note_summary`: `title`, `summary`, `key_points`, `structure`, `formulas`, `definitions`, `pitfalls`, `next_actions`, `confidence`, `needs_manual_review`.
- `image_to_mindmap`: `title`, `root_topic`, `markdown`, `mindmap_json`, `mermaid`, `nodes_count`, `confidence`, `needs_manual_review`.
- `image_to_flashcards`: `title`, `cards`, `confidence`, `needs_manual_review`.
- `image_to_learning_plan`: `diagnosed_level`, `weak_points`, `recommended_path`, `confidence`, `needs_manual_review`.
- `image_to_variant_questions`: `source_question_summary`, `target_knowledge_points`, `variants`, `confidence`, `needs_manual_review`.
- `image_to_resource_bundle`: `understanding`, `explanation`, `note_summary`, `mindmap`, `flashcards`, `wrong_question_analysis`, `weak_points`, `next_actions`, `optional_variants`, `resource_save_candidate`, `knowledge_candidates`, `confidence`, `needs_manual_review`.

`workflow_trace.steps` includes `classify_image_task`, `vision_understanding` for compatibility, `understand_image`, and task-specific steps such as `generate_explanation`, `generate_mindmap`, `generate_flashcards`, `generate_learning_plan`, `generate_variants`, `build_resource_bundle`, `prepare_resource_candidate`, and `prepare_knowledge_candidates`.

## Resource Save And Knowledge Candidates

`POST /api/multimodal/save-resource` stores a user-confirmed multimodal result as a normal resource library entry using the existing `resources` table. No schema migration is required.

`POST /api/multimodal/knowledge-candidates` only returns normalized pending candidates. It does not write the formal knowledge base and never marks a candidate as approved.

All AI-generated resource candidates use `review_status=pending` or equivalent metadata. The frontend may show "待确认"; it must not claim that knowledge has been approved.

Recommended Qwen-VL configuration:

```env
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VL_MODEL=qwen3-vl-plus
```

Do not put API keys in this document.
