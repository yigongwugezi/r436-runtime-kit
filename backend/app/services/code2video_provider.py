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
        """Check if LLM factory has at least one provider configured."""
        from app.services.llm_factory import is_configured as _factory_ok
        import shutil
        return _factory_ok() and shutil.which("manim") is not None

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        import shutil
        if not shutil.which("manim"):
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["Manim is not installed. Run: pip install manim"],
                trace={"required": ["manim CLI"]},
            )

        # Check API keys via unified factory
        from app.services.llm_factory import is_configured as _factory_ok
        if not _factory_ok():
            return _response(
                status="provider_not_configured",
                provider=self.provider,
                warnings=["No LLM provider configured. Set *_API_KEY in .env and check llm_factory.py"],
                trace={"required": ["DEEPSEEK_API_KEY or QWEN_API_KEY or GLM_API_KEY or OPENAI_API_KEY"]},
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

        # ── Step 2: Outline + Storyboard (no rendering yet) ──
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

            agent.generate_outline()
            agent.generate_storyboard()

            # ── Step 2.5: Generate narration per-section BEFORE code ──
            if progress:
                progress({"stage": "narration", "status": "running", "completed_units": 2, "total_units": 5})

            narration_audio_files = []
            for section in agent.sections:
                # Generate concise narration from lecture_lines
                lines_text = "。".join(section.lecture_lines)
                narration_text = self._generate_short_narration(
                    f"{section.title}：{lines_text}", subject, kb_context
                )
                if narration_text and len(narration_text) > 5:
                    agent.section_narrations[section.id] = narration_text
                    audio_path = self._tts_narration(narration_text, f"{job_id}_{section.id}") or self._tts_chattts(narration_text, f"{job_id}_{section.id}")
                    if audio_path:
                        dur = self._get_audio_duration(audio_path)
                        agent.section_durations[section.id] = dur
                        narration_audio_files.append(audio_path)
                        logger.info("Narration for %s: %.1fs", section.id, dur)

            # ── Step 3: Render with duration hints ──
            if progress:
                progress({"stage": "rendering", "status": "running", "completed_units": 3, "total_units": 5})

            for section in agent.sections:
                logger.info(f"Processing: {section.id} - {section.title}")
                agent.render_section(section)
                if cfg.use_feedback and section.id in agent.section_videos:
                    for round_num in range(cfg.feedback_rounds):
                        feedback = agent.get_critic_feedback(section)
                        if feedback:
                            agent.optimize_with_feedback(section, feedback)

            video_path = agent.merge_videos()

            if not video_path or not os.path.isfile(video_path):
                return _response(
                    status="failed",
                    provider=self.provider,
                    warnings=["Code2Video pipeline未能生成视频"],
                    trace={"topic": topic, "work_dir": str(work_dir)},
                )

            logger.info("Code2Video generated: %s", video_path)

            if progress:
                progress({"stage": "rendering", "status": "completed", "completed_units": 4, "total_units": 5})

        except Exception as e:
            logger.warning("Code2Video failed: %s", e)
            return _response(
                status="failed",
                provider=self.provider,
                warnings=[str(e)],
                trace={"topic": topic},
            )

        # ── Step 3: Concatenate per-section narration audio + merge ──
        audio_url = ""
        if narration_audio_files:
            if progress:
                progress({"stage": "narration", "status": "running", "completed_units": 4, "total_units": 5})
            concat_audio = self._concat_audio(narration_audio_files, job_id)
            if concat_audio:
                rel_a = concat_audio.replace("\\", "/")
                outputs_root_a = str(settings.project_root / "outputs").replace("\\", "/") + "/"
                if rel_a.startswith(outputs_root_a):
                    rel_a = rel_a[len(outputs_root_a):]
                audio_url = f"/api/multimodal/file/outputs/{rel_a}"
                merged = self._merge_audio_video(video_path, concat_audio, job_id)
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

        # Collect all narration texts from agent
        all_narration = "\n\n".join(
            agent.section_narrations.get(s.id, "") for s in agent.sections
        ) if hasattr(agent, 'section_narrations') else ""

        return _response(
            status="success",
            provider=self.provider,
            result={
                "video_url": url,
                "local_path": video_path,
                "audio_url": audio_url,
                "narration_text": all_narration,
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
    def _generate_short_narration(content: str, subject: str, kb_context: str) -> str:
        """Generate a SHORT narration for a single section."""
        kb_block = f"\n知识点参考：{kb_context[:500]}" if kb_context else ""
        prompt = (
            f"把以下教学要点写成一句中文讲解旁白，自然口语，20-40字。\n"
            f"课程: {subject}\n要点: {content}{kb_block}\n只输出旁白。"
        )
        try:
            from app.services.llm_client import get_llm_client
            llm = get_llm_client()
            return llm.chat(
                messages=[
                    {"role": "system", "content": "你是老师。把要点写成一句口语旁白。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3, max_tokens=200,
            ).strip()
        except Exception:
            return content[:50]

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration via FFmpeg."""
        import shutil as _s, subprocess, re as _re
        ffmpeg = _s.which("ffmpeg")
        if not ffmpeg:
            for c in [r"C:\\Users\\hejiaxuan\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-8.1.2-full_build\\bin\\ffmpeg.exe"]:
                if os.path.isfile(c): ffmpeg = c; break
        if not ffmpeg: return 5.0
        try:
            r = subprocess.run([str(ffmpeg), "-i", audio_path, "-f", "null", "-"],
                capture_output=True, text=True, timeout=10)
            m = _re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
            if m: return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
        except: pass
        return 5.0

    def _concat_audio(self, audio_files: list, job_id: str) -> str:
        """Concatenate multiple audio files with FFmpeg."""
        import shutil as _s, subprocess
        ffmpeg = _s.which("ffmpeg")
        if not ffmpeg:
            for c in [r"C:\\Users\\hejiaxuan\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-8.1.2-full_build\\bin\\ffmpeg.exe"]:
                if os.path.isfile(c): ffmpeg = c; break
        if not ffmpeg: return ""
        if len(audio_files) == 1: return audio_files[0]
        list_file = self.output_dir / f"{job_id}_audio_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for af in audio_files: f.write(f"file '{af}'\n")
        out = self.output_dir / f"{job_id}_narration_combined.wav"
        try:
            r = subprocess.run([str(ffmpeg), "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file), "-c", "copy", str(out)],
                capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and out.exists(): return str(out)
        except: pass
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
