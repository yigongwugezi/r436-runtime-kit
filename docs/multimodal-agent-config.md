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
