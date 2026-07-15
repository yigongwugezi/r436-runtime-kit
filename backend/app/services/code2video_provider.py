"""Code2Video Provider — Adapter between EduAgent's multimodal interface and Code2Video.

Replaces the simple LLM→Manim approach with a multi-agent pipeline:
  Planner (DeepSeek) → Storyboard → Coder (Qwen-Coder) → Critic (Qwen-VL)

Existing features preserved: RAG retrieval, Chinese narration/TTS, FFmpeg audio-video merge.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _response(
    *,
    status: str,
    provider: str,
    result: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "provider": provider,
        "result": result or {},
        "warnings": warnings or [],
        "trace": trace or {},
    }


class Code2VideoProvider:
    """Generate educational videos via Code2Video multi-agent pipeline."""

    name = "Code2VideoProvider"
    provider = "code2video"

    @property
    def output_dir(self) -> Path:
        d = settings.project_root / "outputs" / "code2video"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def is_configured() -> bool:
        """Check if at least one of DeepSeek or Qwen API is configured."""
        ds_key = os.getenv("DEEPSEEK_API_KEY", "")
        qwen_key = os.getenv("QWEN_API_KEY", "")
        import shutil
        has_manim = shutil.which("manim") is not None
        return bool(ds_key or qwen_key) and has_manim

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        import shutil
        if not shutil.which("manim"):
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["Manim is not installed. Run: pip install manim"],
                trace={"required": ["manim CLI"]},
            )

        # Check API keys — at least one must be configured
        ds_key = os.getenv("DEEPSEEK_API_KEY", "")
        qwen_key = os.getenv("QWEN_API_KEY", "")
        if not ds_key and not qwen_key:
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["DEEPSEEK_API_KEY or QWEN_API_KEY not set. Switch to ManimVideoProvider."],
                trace={"required": ["DEEPSEEK_API_KEY", "QWEN_API_KEY"]},
            )

        topic = self._extract_topic(context)
        subject = str(context.get("subject_name") or topic)
        kp_text = str(context.get("knowledge_points") or "")

        logger.info("Code2Video: topic=%s subject=%s", topic, subject)

        # ── Step 1: RAG retrieval (reuse existing) ──
        kb_context = self._rag_retrieve(topic)

        progress = context.get("progress_callback")
        cancel = context.get("cancel_event")

        if progress:
            progress({"stage": "rag_retrieval", "status": "completed", "completed_units": 1, "total_units": 5})

        # ── Step 2: Run Code2Video pipeline ──
        job_id = uuid.uuid4().hex
        work_dir = self.output_dir / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        if progress:
            progress({"stage": "outline", "status": "running", "completed_units": 1, "total_units": 5})

        try:
            from app.code2video.agent import TeachingVideoAgent, RunConfig
            from app.code2video.gpt_request import (
                request_deepseek_token,
                request_qwen_token,
                request_qwen_vl_frames,
            )

            cfg = RunConfig(
                planner_api=request_deepseek_token,
                coder_api=request_qwen_token,
                critic_api=request_qwen_vl_frames,
                use_feedback=True,
                feedback_rounds=1,
            )

            agent = TeachingVideoAgent(
                knowledge_point=f"{subject}——{topic}",
                output_dir=work_dir,
                idx=0,
                cfg=cfg,
            )

            video_path = agent.GENERATE_VIDEO()

            if not video_path or not os.path.isfile(video_path):
                return _response(
                    status="failed",
                    provider=self.provider,
                    warnings=["Code2Video pipeline未能生成视频"],
                    trace={"topic": topic, "work_dir": str(work_dir)},
                )

            logger.info("Code2Video generated: %s", video_path)

            if progress:
                progress({"stage": "rendering", "status": "completed", "completed_units": 3, "total_units": 5})

        except Exception as e:
            logger.warning("Code2Video failed: %s", e)
            return _response(
                status="failed",
                provider=self.provider,
                warnings=[str(e)],
                trace={"topic": topic},
            )

        # ── Step 3: Generate Chinese narration + ChatTTS (precise audio) ──
        if progress:
            progress({"stage": "narration", "status": "running", "completed_units": 4, "total_units": 5})

        narration_text = self._generate_narration(topic, subject, kb_context)
        audio_path = ""
        audio_url = ""
        if narration_text and len(narration_text) > 20:
            audio_path = self._tts_chattts(narration_text, job_id) or self._tts_narration(narration_text, job_id)
            if audio_path:
                rel_a = audio_path.replace("\\", "/")
                outputs_root_a = str(settings.project_root / "outputs").replace("\\", "/") + "/"
                if rel_a.startswith(outputs_root_a):
                    rel_a = rel_a[len(outputs_root_a):]
                audio_url = f"/api/multimodal/file/outputs/{rel_a}"
                # Merge audio into video
                merged = self._merge_audio_video(video_path, audio_path, job_id)
                if merged:
                    video_path = merged

        # ── Step 4: Move to final location, build URL ──
        import shutil as _shutil
        final_dir = self.output_dir
        final_name = f"{job_id}_final.mp4"
        final_path = final_dir / final_name
        try:
            _shutil.move(str(video_path), str(final_path))
            video_path = str(final_path)
        except Exception:
            final_path = Path(video_path)
            final_dir = final_path.parent
            final_name = final_path.name

        rel = video_path.replace("\\", "/")
        outputs_root = str(settings.project_root / "outputs").replace("\\", "/") + "/"
        if rel.startswith(outputs_root):
            rel = rel[len(outputs_root):]
        url = f"/api/multimodal/file/outputs/{rel}"

        return _response(
            status="success",
            provider=self.provider,
            result={
                "video_url": url,
                "local_path": video_path,
                "audio_url": audio_url,
                "narration_text": narration_text,
            },
        )

    # ── Helper methods (reused from ManimVideoProvider) ────────────────

    @staticmethod
    def _extract_topic(context: dict) -> str:
        topic = str(context.get("topic") or context.get("user_message") or "")
        topic = re.sub(r"^(我需要|我要|帮我|请|给我)(讲解|生成|做一个|出一个)?", "", topic)
        topic = re.sub(r"(的教学视频|的视频|的微课视频|的视频教程|的动画)$", "", topic).strip()
        return topic or "未命名知识点"

    @staticmethod
    def _rag_retrieve(topic: str) -> str:
        try:
            from app.rag.query_engine import rag_query_engine
            if rag_query_engine.is_ready():
                resp = rag_query_engine.search(topic, top_k=3)
                if resp.results:
                    return "\n\n".join(
                        f"## {r.title}\n{r.text[:800]}"
                        for r in resp.results if r.text
                    )
        except Exception:
            pass
        return ""

    @staticmethod
    def _generate_narration(topic: str, subject: str, kb_context: str) -> str:
        kb_block = f"\n知识点参考：{kb_context[:800]}" if kb_context else ""
        prompt = (
            f"为以下知识点写一段中文旁白讲解稿。像老师正常讲课，把该讲的讲清楚。"
            f"引入→原理→例子→总结。逗号句号停顿。自然口语。\n"
            f"课程: {subject}\n节: {topic}{kb_block}\n只输出旁白。"
        )
        try:
            from app.services.llm_client import get_llm_client
            llm = get_llm_client()
            raw = llm.chat(
                messages=[
                    {"role": "system", "content": "你是数学老师。写中文旁白，自然口语。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            return raw.strip()
        except Exception:
            return ""

    def _tts_narration(self, text: str, job_id: str) -> str:
        import shutil as _s
        edge_tts = _s.which("edge-tts")
        if not edge_tts:
            for candidate in [
                r"C:\Users\hejiaxuan\AppData\Local\Programs\Python\Python313\Scripts\edge-tts.EXE",
            ]:
                if os.path.isfile(candidate):
                    edge_tts = candidate
                    break
        if not edge_tts:
            return ""
        try:
            import subprocess
            mp3_path = self.output_dir / f"{job_id}_narration.mp3"
            result = subprocess.run(
                [edge_tts, "--voice", "zh-CN-XiaoxiaoNeural",
                 "--text", text, "--write-media", str(mp3_path)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and mp3_path.exists():
                return str(mp3_path)
        except Exception:
            pass
        return ""

    def _tts_chattts(self, text: str, job_id: str) -> str:
        """Use ChatTTS for high-quality Chinese TTS. Falls back to edge-tts if not installed."""
        try:
            from ChatTTS import Chat
            import numpy as np
            chat = Chat()
            chat.load(compile=False)
            texts = [s.strip() for s in text.replace('\n', '。').split('。') if s.strip()]
            if not texts:
                return ""
            wavs = chat.infer(texts, use_decoder=True)
            import soundfile as sf
            wav_path = self.output_dir / f"{job_id}_narration_chattts.wav"
            combined = np.concatenate([w for w in wavs])
            sf.write(str(wav_path), combined, 24000)
            if wav_path.exists():
                logger.info("ChatTTS generated: %s (%d segments)", wav_path, len(texts))
                return str(wav_path)
        except ImportError:
            logger.info("ChatTTS not installed, using edge-tts fallback")
        except Exception as e:
            logger.warning("ChatTTS failed: %s, falling back to edge-tts", e)
        return ""

    def _merge_audio_video(self, video_path: str, audio_path: str, job_id: str) -> str:
        import shutil as _shutil, subprocess, re as _re
        ffmpeg = _shutil.which("ffmpeg")
        if not ffmpeg:
            for candidate in [
                r"C:\Users\hejiaxuan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
            ]:
                if os.path.isfile(candidate):
                    ffmpeg = candidate
                    break
        if not ffmpeg:
            return ""
        try:
            merged_path = self.output_dir / f"{job_id}_with_audio.mp4"
            result = subprocess.run([
                str(ffmpeg), "-y",
                "-i", video_path, "-i", audio_path,
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", str(merged_path),
            ], capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and merged_path.exists():
                return str(merged_path)
        except Exception:
            pass
        return ""
