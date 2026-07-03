# Image AI Web Acceptance

Use a fresh browser chat session unless a case says "same session".

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

   Expected: normal chat text is the main answer; extraction details are collapsed.

2. Same session, no new upload:

   ```text
   继续讲第2题
   ```

   Expected: reuses the previous image/questions.

3. Same session, no new upload:

   ```text
   根据这张图生成思维导图
   ```

   Expected: Markmap renders; markdown fallback is available.

4. Same session, no new upload:

   ```text
   根据这张图生成复习卡片
   ```

   Expected: cards are generated from the cached vision result.

5. Same session, no new upload:

   ```text
   根据这张图生成完整学习资源包
   ```

   Expected: resource and knowledge candidates are pending, not approved.

6. New chat, no upload:

   ```text
   根据这张图生成思维导图
   ```

   Expected: asks for an image instead of using the old session image.

7. Upload another image:

   ```text
   识别这张图片
   ```

   Then send:

   ```text
   继续讲第1题
   ```

   Expected: uses the new image, not the previous one.

## Optional API Smoke

This does not require a real API key:

```powershell
cd C:\Users\20825\Documents\Codex\2026-06-07\seedance-ai-claude-code-ai-ai\backend
$env:PYTHONIOENCODING="utf-8"
.venv310\Scripts\python.exe tests\multimodal_agent_test.py
.venv310\Scripts\python.exe tests\multimodal_router_test.py
.venv310\Scripts\python.exe tests\product_chat_boundary_test.py
```
