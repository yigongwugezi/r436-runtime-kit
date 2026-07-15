"""Code2Video TeachingVideoAgent — adapted for EduAgent with domestic LLMs.

Agent pipeline:
  Planner (DeepSeek) → Storyboard (DeepSeek) → Coder (Qwen-Coder) → Critic (Qwen-VL)

Adapted from: showlab/Code2Video (ICML 2026)
"""
import json
import os
import time
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable

from . import gpt_request as api
from .prompts import (
    base_class,
    get_prompt1_outline,
    get_prompt2_storyboard,
    get_prompt3_code,
    get_regenerate_note,
    get_prompt4_layout_feedback,
    get_feedback_list_prefix,
    get_feedback_improve_code,
)
from .utils import (
    extract_json_from_markdown,
    extract_answer_from_response,
    replace_base_class,
    get_output_dir,
    extract_video_frames,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Section:
    id: str
    title: str
    lecture_lines: List[str]
    animations: List[str]


@dataclass
class RunConfig:
    """Configuration for a Code2Video run."""
    # API functions — planner uses DeepSeek, coder uses Qwen
    planner_api: Callable = field(default_factory=lambda: api.request_deepseek_token)
    coder_api: Callable = field(default_factory=lambda: api.request_qwen_token)
    critic_api: Callable = field(default_factory=lambda: api.request_qwen_vl_frames)
    
    # Features
    use_feedback: bool = True
    feedback_rounds: int = 1
    
    # Limits
    max_code_token_length: int = 8000
    max_fix_bug_tries: int = 5
    max_regenerate_tries: int = 3
    max_feedback_gen_code_tries: int = 2
    max_mllm_fix_bugs_tries: int = 2


# ═══════════════════════════════════════════════════════════════════════
# Main Agent
# ═══════════════════════════════════════════════════════════════════════

class TeachingVideoAgent:
    """Generate educational Manim videos from knowledge points."""
    
    def __init__(
        self,
        knowledge_point: str,
        output_dir: Path,
        idx: int = 0,
        cfg: Optional[RunConfig] = None,
    ):
        self.learning_topic = knowledge_point
        self.idx = idx
        self.cfg = cfg or RunConfig()
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # State
        self.outline = None
        self.storyboard_data = None
        self.sections: List[Section] = []
        self.section_codes: Dict[str, str] = {}
        self.section_videos: Dict[str, str] = {}
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # Reference image path (optional)
        self.reference_img_path = None
        # Per-section narration durations (set externally before rendering)
        self.section_durations: Dict[str, float] = {}
        self.section_narrations: Dict[str, str] = {}
    
    def _track_tokens(self, usage: Optional[Dict]) -> None:
        if usage:
            self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
    
    # ── Stage 1: Outline ────────────────────────────────────────────
    
    def generate_outline(self) -> Dict:
        """Generate teaching outline from knowledge point."""
        outline_file = self.output_dir / "outline.json"
        
        if outline_file.exists():
            with open(outline_file, "r", encoding="utf-8") as f:
                self.outline = json.load(f)
            logger.info("Loaded cached outline")
            return self.outline
        
        prompt = get_prompt1_outline(knowledge_point=self.learning_topic)
        
        for attempt in range(self.cfg.max_regenerate_tries):
            response, usage = self.cfg.planner_api(
                prompt, max_tokens=self.cfg.max_code_token_length
            )
            self._track_tokens(usage)
            
            if response is None:
                continue
            
            try:
                content = response.choices[0].message.content
                content = extract_json_from_markdown(content)
                self.outline = json.loads(content)
                
                with open(outline_file, "w", encoding="utf-8") as f:
                    json.dump(self.outline, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Outline generated: {self.outline.get('topic', 'N/A')}")
                return self.outline
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Outline attempt {attempt+1} failed: {e}")
        
        raise ValueError("Failed to generate outline after multiple attempts")
    
    # ── Stage 2: Storyboard ─────────────────────────────────────────
    
    def generate_storyboard(self) -> List[Section]:
        """Generate detailed storyboard from outline."""
        if not self.outline:
            raise ValueError("Outline not generated yet")
        
        storyboard_file = self.output_dir / "storyboard.json"
        
        if storyboard_file.exists():
            with open(storyboard_file, "r", encoding="utf-8") as f:
                self.storyboard_data = json.load(f)
            logger.info("Loaded cached storyboard")
        else:
            outline_json = json.dumps(self.outline, ensure_ascii=False, indent=2)
            prompt = get_prompt2_storyboard(outline=outline_json, reference_image_path=None)
            
            for attempt in range(self.cfg.max_regenerate_tries):
                response, usage = self.cfg.planner_api(
                    prompt, max_tokens=self.cfg.max_code_token_length
                )
                self._track_tokens(usage)
                
                if response is None:
                    continue
                
                try:
                    content = response.choices[0].message.content
                    content = extract_json_from_markdown(content)
                    self.storyboard_data = json.loads(content)
                    
                    with open(storyboard_file, "w", encoding="utf-8") as f:
                        json.dump(self.storyboard_data, f, ensure_ascii=False, indent=2)
                    break
                except json.JSONDecodeError:
                    logger.warning(f"Storyboard attempt {attempt+1} format invalid")
        
        # Parse into Section objects
        self.sections = []
        for sec_data in self.storyboard_data.get("sections", []):
            section = Section(
                id=sec_data["id"],
                title=sec_data["title"],
                lecture_lines=sec_data.get("lecture_lines", []),
                animations=sec_data.get("animations", []),
            )
            self.sections.append(section)
        
        logger.info(f"Storyboard: {len(self.sections)} sections")
        return self.sections
    
    # ── Stage 3: Code Generation ────────────────────────────────────
    
    def generate_section_code(self, section: Section, attempt: int = 1,
                              feedback: Optional[List[str]] = None) -> str:
        """Generate Manim code for a single section."""
        code_file = self.output_dir / f"{section.id}.py"
        
        # Return cached if available and no feedback override
        if attempt == 1 and not feedback and code_file.exists():
            code = code_file.read_text(encoding="utf-8")
            self.section_codes[section.id] = code
            return code
        
        if feedback:
            current_code = self.section_codes.get(section.id, "")
            prompt = get_feedback_improve_code(
                feedback=get_feedback_list_prefix(feedback),
                code=current_code
            )
        else:
            regenerate_note = get_regenerate_note(attempt, self.cfg.max_regenerate_tries) if attempt > 1 else ""
            prompt = get_prompt3_code(
                regenerate_note=regenerate_note,
                section=section,
                base_class=base_class,
            )
            # Add duration hint if narration duration is known
            if section.id in self.section_durations:
                dur = self.section_durations[section.id]
                prompt += f"\n\n动画总时长必须精确为 {dur:.1f} 秒。每段动画的 self.wait() 总加和要等于 {dur:.1f} 秒。"
        
        response, usage = self.cfg.coder_api(
            prompt, max_tokens=self.cfg.max_code_token_length
        )
        self._track_tokens(usage)
        
        if response is None:
            return ""
        
        try:
            code = response.choices[0].message.content
        except Exception:
            return ""
        
        # Extract code from markdown
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].strip()
        
        # Replace base class definition
        code = replace_base_class(code, base_class)
        
        # Ensure imports
        if "from manim import" not in code:
            code = "from manim import *\n" + code
        if "import numpy as np" not in code:
            code = code.replace("from manim import *", "from manim import *\nimport numpy as np")
        
        # Prevent SVGMobject/ImageMobject calls
        import re
        code = re.sub(r'SVGMobject\s*\([^)]*\)', 'Circle()', code)
        code = re.sub(r'ImageMobject\s*\([^)]*\)', 'Square()', code)
        
        # Fix common formula rendering issues
        code = self._fix_formulas(code)
        
        code_file.write_text(code, encoding="utf-8")
        self.section_codes[section.id] = code
        return code

    @staticmethod
    def _fix_formulas(code: str) -> str:
        """Fix common LLM formula issues: $$ delimiters, unbalanced braces."""
        import re
        code = re.sub(r'MathTex\(r"\$([^"]+)\$"\)', r'MathTex(r"\1")', code)
        code = re.sub(r'(MathTex\([^)]*?)\$\$', r'\1', code)
        code = re.sub(r'\$\$([^)]*?\))', r'\1', code)
        code = re.sub(r'Text\("[^"]*\$\$[^"]*"\)', lambda m: m.group().replace('$$', ''), code)
        return code
    
    # ── Render & Debug ──────────────────────────────────────────────
    
    def debug_and_fix_code(self, section_id: str, max_fix_attempts: int = 5) -> bool:
        """Render Manim code and fix errors up to max attempts."""
        if section_id not in self.section_codes:
            return False
        
        for fix_attempt in range(max_fix_attempts):
            scene_name = f"{section_id.title().replace('_', '')}Scene"
            code_file = self.output_dir / f"{section_id}.py"
            
            try:
                result = subprocess.run(
                    ["manim", "-ql", str(code_file), scene_name],
                    capture_output=True, text=True, timeout=180,
                    cwd=str(self.output_dir),
                )
            except subprocess.TimeoutExpired:
                logger.warning(f"Render timeout for {section_id}")
                continue
            
            if result.returncode == 0:
                # Find output video
                media_dir = self.output_dir / "media"
                for pattern in [
                    f"**/{scene_name}.mp4",
                    f"**/480p15/{scene_name}.mp4",
                    "**/*.mp4",
                ]:
                    candidates = list(media_dir.glob(pattern)) if media_dir.exists() else []
                    if candidates:
                        self.section_videos[section_id] = str(candidates[0])
                        logger.info(f"Rendered: {section_id}")
                        return True
            
            # Fix attempt
            if fix_attempt < max_fix_attempts - 1:
                error_msg = (result.stderr or "")[-2000:]
                logger.warning(f"Render failed for {section_id}, attempt {fix_attempt+1}: {error_msg[:200]}")
                
                # Ask LLM to fix
                fix_prompt = f"""Fix this broken Manim script.

Error:
{error_msg}

Code:
```python
{self.section_codes.get(section_id, '')}
```

Fix ALL bugs. Output only corrected Python code.
Use MathTex() for formulas, Text() for Chinese. No SVGMobject/ImageMobject."""
                
                response, usage = self.cfg.coder_api(fix_prompt, max_tokens=6000)
                self._track_tokens(usage)
                
                if response:
                    try:
                        fixed = response.choices[0].message.content
                        if "```python" in fixed:
                            fixed = fixed.split("```python")[1].split("```")[0].strip()
                        elif "```" in fixed:
                            fixed = fixed.split("```")[1].strip()
                        
                        if "class" in fixed:
                            # Ensure imports
                            if "from manim import" not in fixed:
                                fixed = "from manim import *\n" + fixed
                            if "import numpy as np" not in fixed:
                                fixed = fixed.replace("from manim import *", "from manim import *\nimport numpy as np")
                            
                            import re as _re
                            fixed = _re.sub(r'SVGMobject\s*\([^)]*\)', 'Circle()', fixed)
                            fixed = _re.sub(r'ImageMobject\s*\([^)]*\)', 'Square()', fixed)
                            
                            code_file.write_text(fixed, encoding="utf-8")
                            self.section_codes[section_id] = fixed
                            continue
                    except Exception:
                        pass
            
            logger.warning(f"Could not fix {section_id} after {fix_attempt+1} attempts")
        
        return False
    
    def render_section(self, section: Section) -> bool:
        """Full pipeline for a single section: generate code → render → fix."""
        section_id = section.id
        
        for attempt in range(self.cfg.max_regenerate_tries):
            self.generate_section_code(section, attempt=attempt + 1)
            success = self.debug_and_fix_code(
                section_id, max_fix_attempts=self.cfg.max_fix_bug_tries
            )
            if success:
                break
        
        return section_id in self.section_videos
    
    def render_all_sections(self) -> Dict[str, str]:
        """Render all sections sequentially."""
        for section in self.sections:
            logger.info(f"Rendering section: {section.id} - {section.title}")
            self.render_section(section)
        
        # Filter successful renders
        for sid in list(self.section_videos.keys()):
            video_path = self.section_videos[sid]
            if not os.path.isfile(video_path):
                del self.section_videos[sid]
        
        logger.info(f"Rendered {len(self.section_videos)}/{len(self.sections)} sections")
        return self.section_videos
    
    # ── Stage 4: Critic (Visual Feedback) ───────────────────────────
    
    def get_critic_feedback(self, section: Section) -> Optional[List[str]]:
        """Extract video frames and get visual feedback from Qwen-VL."""
        section_id = section.id
        if section_id not in self.section_videos:
            return None
        
        video_path = self.section_videos[section_id]
        frames_dir = self.output_dir / "critic_frames" / section_id
        
        frame_paths = extract_video_frames(video_path, frames_dir, num_frames=3)
        if not frame_paths:
            logger.warning(f"Failed to extract frames for {section_id}")
            return None
        
        prompt = f"""你是一位教学视频评估专家。请检查这段教学动画的3帧截图（视频开头、中间、结尾）。

主题: {section.title}
讲解要点: {'; '.join(section.lecture_lines)}

请逐条列出看到的问题（最多5条），每条格式：问题描述 + 建议的修改方案。
关注以下方面：
1. 画面元素是否完整（有无遮挡、缺失）
2. 文字和公式是否清晰可读
3. 整体布局是否合理
4. 颜色搭配是否舒适

用中文简要回答。"""
        
        try:
            response, usage = self.cfg.critic_api(
                prompt, image_paths=frame_paths, max_tokens=2000
            )
            self._track_tokens(usage)
            
            if response:
                content = response.choices[0].message.content
                # Extract bullet points
                import re
                lines = content.strip().split("\n")
                issues = [l.strip("- 0123456789.。 ") for l in lines if l.strip() and len(l.strip()) > 10]
                return issues[:5] if issues else None
        except Exception as e:
            logger.warning(f"Critic feedback failed: {e}")
        
        return None
    
    def optimize_with_feedback(self, section: Section, feedback: List[str]) -> bool:
        """Re-generate code based on Critic feedback."""
        for attempt in range(self.cfg.max_feedback_gen_code_tries):
            new_code = self.generate_section_code(
                section, attempt=attempt + 1, feedback=feedback
            )
            if not new_code:
                continue
            
            success = self.debug_and_fix_code(
                section.id, max_fix_attempts=self.cfg.max_mllm_fix_bugs_tries
            )
            if success:
                return True
        
        return False
    
    # ── Final Merge ─────────────────────────────────────────────────
    
    def merge_videos(self) -> Optional[str]:
        """Merge all section videos into a single video."""
        if not self.section_videos:
            return None
        
        sorted_videos = []
        for section in self.sections:
            if section.id in self.section_videos:
                sorted_videos.append(self.section_videos[section.id])
        
        if len(sorted_videos) == 0:
            return None
        if len(sorted_videos) == 1:
            return sorted_videos[0]
        
        # Use FFmpeg concat
        import shutil as _sh
        ffmpeg = _sh.which("ffmpeg")
        if not ffmpeg:
            for candidate in [
                r"C:\Users\hejiaxuan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
            ]:
                if os.path.isfile(candidate):
                    ffmpeg = candidate
                    break
        
        if not ffmpeg:
            logger.warning("FFmpeg not found, returning first video only")
            return sorted_videos[0]
        
        list_file = self.output_dir / "video_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for vp in sorted_videos:
                # Use absolute paths for FFmpeg concat
                f.write(f"file '{vp}'\n")
        
        output_path = self.output_dir / "final_video.mp4"
        try:
            subprocess.run(
                [str(ffmpeg), "-y", "-f", "concat", "-safe", "0",
                 "-i", str(list_file), "-c", "copy", str(output_path)],
                capture_output=True, text=True, timeout=60,
            )
            if output_path.exists():
                return str(output_path)
        except Exception as e:
            logger.warning(f"Video merge failed: {e}")
        
        return sorted_videos[0]
    
    # ── Main Pipeline ───────────────────────────────────────────────
    
    def GENERATE_VIDEO(self) -> Optional[str]:
        """Run the full Code2Video pipeline."""
        try:
            # Stage 1: Outline
            self.generate_outline()
            
            # Stage 2: Storyboard
            self.generate_storyboard()
            
            # Stage 3: Generate + render all sections
            for section in self.sections:
                logger.info(f"Processing: {section.id} - {section.title}")
                
                # Generate + render
                self.render_section(section)
                
                # Stage 4: Critic feedback (if enabled)
                if self.cfg.use_feedback and section.id in self.section_videos:
                    for round_num in range(self.cfg.feedback_rounds):
                        feedback = self.get_critic_feedback(section)
                        if feedback:
                            logger.info(f"Critic round {round_num+1}: {len(feedback)} issues")
                            self.optimize_with_feedback(section, feedback)
            
            # Merge
            final_video = self.merge_videos()
            if final_video:
                logger.info(f"Video generated: {final_video}")
                return final_video
            else:
                logger.error("No videos generated")
                return None
                
        except Exception as e:
            logger.error(f"Video generation failed: {e}", exc_info=True)
            return None
