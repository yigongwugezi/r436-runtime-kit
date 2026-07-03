# Image AI Web Acceptance

Use a fresh browser chat session unless a case says `same session`.

## Start Services

Backend:

```powershell
cd C:\Users\20825\Documents\Codex\2026-06-07\seedance-ai-claude-code-ai-ai\backend
$env:PYTHONIOENCODING="utf-8"
.venv310\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd C:\Users\20825\Documents\Codex\2026-06-07\seedance-ai-claude-code-ai-ai\frontend
npm run dev
```

Open [http://localhost:5173/](http://localhost:5173/).

## Smoke Cases

1. Upload a question image and send:

   ```text
   请详细讲解这张图片里的题目，并指出每道题考查的知识点
   ```

   Expected: normal chat text is the main answer; the user message shows a thumbnail; extraction details are collapsed behind `查看识别详情`.

2. Same session, no new upload:

   ```text
   继续讲第2题
   ```

   Expected: the input chip says it is using the previous image; the reply uses the previous extracted questions and remains normal chat text.

3. Same session, no new upload:

   ```text
   根据这张图生成思维导图
   ```

   Expected: the chip appears, Markmap renders first, and OCR details stay collapsed.

4. Same session, no new upload:

   ```text
   根据这张图生成复习卡片
   ```

   Expected: cards are generated from the cached vision result; front is visible, back is folded, and math is rendered where possible.

5. Same session, no new upload:

   ```text
   根据这张图生成完整学习资源包
   ```

   Expected: empty sections and `..` placeholders are hidden; resource and knowledge candidates remain pending, not automatically approved.

6. Same session, type an image reference and then click `取消引用` before sending:

   ```text
   根据这张图生成思维导图
   ```

   Expected: the current message does not use the cached image and asks for an image if no new upload is attached.

7. Same session, ordinary text:

   ```text
   你好
   帮我生成几道练习题
   今天学习计划怎么安排
   解释一下导数
   ```

   Expected: no last-image chip appears, no image is attached automatically, and the message stays in the normal chat path.

8. New chat, no upload:

   ```text
   根据这张图生成思维导图
   ```

   Expected: asks for an image instead of using an old session image.

9. Upload another image:

   ```text
   识别这张图片
   ```

   Then send:

   ```text
   继续讲第1题
   ```

   Expected: uses the new image, not the previous one.

10. If `needs_manual_review=true`, verify that the UI lists concrete reasons, question numbers, uncertain fields, and whether the result can still be used. It should not show only a generic error.

## Optional API Smoke

This does not require a real API key:

```powershell
cd C:\Users\20825\Documents\Codex\2026-06-07\seedance-ai-claude-code-ai-ai\backend
$env:PYTHONIOENCODING="utf-8"
.venv310\Scripts\python.exe tests\multimodal_agent_test.py
.venv310\Scripts\python.exe tests\multimodal_router_test.py
.venv310\Scripts\python.exe tests\product_chat_boundary_test.py
```
