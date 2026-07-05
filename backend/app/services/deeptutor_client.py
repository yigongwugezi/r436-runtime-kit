"""Shared DeepTutor client — sync interface for LangGraph nodes."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import nest_asyncio

logger = logging.getLogger(__name__)

nest_asyncio.apply()


def _setup_config():
    if not os.environ.get("LLM_API_KEY"):
        return False
    try:
        from deeptutor.services.llm.config import LLMConfig, set_scoped_llm_config
        cfg = LLMConfig(
            model=os.environ.get("LLM_MODEL", "qwen-plus"),
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL", ""),
            effective_url=os.environ.get("LLM_BASE_URL", ""),
            binding="openai", provider_name="openai_compatible", provider_mode="cloud",
        )
        set_scoped_llm_config(cfg)
        os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]
        os.environ["OPENAI_BASE_URL"] = os.environ.get("LLM_BASE_URL", "")
        return True
    except Exception as e:
        logger.debug("DT config: %s", e)
        return False


def deeptutor_call(capability: str, message: str, history: list | None = None) -> str:
    if not _setup_config():
        return ""

    async def _go():
        from deeptutor.runtime import ChatOrchestrator
        from deeptutor.core.context import UnifiedContext
        from deeptutor.core.stream import StreamEventType
        ctx = UnifiedContext(user_message=message, conversation_history=history or [], language="zh")
        if capability and capability != "chat":
            ctx.active_capability = capability
        parts = []
        async for event in ChatOrchestrator().handle(ctx):
            if event.type == StreamEventType.CONTENT:
                parts.append(str(event.content or ""))
        return "".join(parts)

    try:
        return asyncio.run(_go())
    except Exception as e:
        logger.warning("DeepTutor %s failed: %s", capability, e)
        return ""


def generate_quiz(topic: str, knowledge_points: str = "", count: int = 5) -> str:
    prompt = f"生成{count}道关于'{topic}'的练习题。知识点：{knowledge_points}。题型混合选择/填空/判断/简答，含答案和解析。"
    return deeptutor_call("chat", prompt)


def generate_research(topic: str) -> str:
    return deeptutor_call("chat", f"对'{topic}'进行深度研究，提供结构化拓展阅读材料，包含背景、核心概念、应用案例。2000字以上。")


def generate_mindmap(topic: str) -> str:
    return deeptutor_call("chat", f"为'{topic}'生成一个Mermaid格式的思维导图，覆盖关键知识点和层级关系。只输出mermaid代码块。")


def generate_visual_explanation(topic: str) -> str:
    """Generate a visual diagram/illustration explaining a concept."""
    prompt = f"用图解方式解释'{topic}'。生成一个Mermaid图表（流程图、时序图或类图），配合简洁的文字说明，让学生一目了然。输出Mermaid代码块加简短文字。"
    return deeptutor_call("chat", prompt)


def generate_video_script(topic: str, duration_minutes: int = 3) -> str:
    """Generate an educational video script with scenes, narration, and visuals."""
    body_minutes = duration_minutes - 1
    prompt = (
        f"为'{topic}'生成一个{duration_minutes}分钟的教学微课视频脚本。\n"
        f"包含以下结构：\n"
        f"1. 片头（30秒）：标题、学习目标\n"
        f"2. 核心讲解（{body_minutes}分钟）：分3-5个场景，每场景标注时长、画面描述、配音文字\n"
        f"3. 片尾（30秒）：小结、思考题\n"
        f"输出格式化为场景列表，标注时间轴。"
    )
    return deeptutor_call("chat", prompt)


def generate_lecture(topic: str) -> str:
    """Generate a comprehensive illustrated lecture with diagrams."""
    prompt = (
        f"为「{topic}」生成一份图文并茂的完整讲义。\n"
        "要求：Markdown格式，含课程概述、学习目标、核心知识体系（3-5个模块）、"
        "每个模块配Mermaid流程图/时序图、关键概念详细解释含示例、常见误区、课后3道思考题。"
        "1500字以上，嵌入至少2个Mermaid图表。"
    )
    # Try DeepTutor first, fall back to our LLM
    result = deeptutor_call("chat", prompt)
    if result and len(result) > 500 and 'mermaid' in result.lower():
        return result
    # Fall back to our LLM
    try:
        from app.services.llm_client import get_llm_client
        from app.config import settings
        c = get_llm_client(settings.llm_provider)
        return c.chat(messages=[{"role": "user", "content": prompt}], temperature=0.5, max_tokens=3000)
    except Exception:
        return result or ""


def generate_manim_video(topic: str) -> dict | None:
    """Generate script via LLM, render via Manim. Returns {'path':str, 'title':str} or None."""
    import tempfile, os, uuid, subprocess, sys

    # Step 1: Generate script via LLM
    script = deeptutor_call("chat",
        f"为'{topic}'写Manim动画代码。只用Text和Write，3-5个关键概念依次显示。"
        f"class名为TopicScene，继承Scene。只输出Python代码，不要解释。"
    )
    if not script or len(script) < 20:
        return None

    # Extract code
    code = script
    for marker in ['```python', '```']:
        if marker in code:
            parts = code.split(marker)
            for p in parts:
                if 'class' in p and 'Scene' in p:
                    code = p
                    break
    code = code.strip()
    if 'from manim' not in code[:200]:
        code = 'from manim import *\n\n' + code

    # Step 2: Render via subprocess
    tmpdir = tempfile.mkdtemp()
    script_path = os.path.join(tmpdir, 'scene.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(code)

    try:
        result = subprocess.run(
            [sys.executable, '-m', 'manim', '-ql', '--format', 'mp4',
             script_path, 'TopicScene', '-o', f'{uuid.uuid4().hex[:8]}.mp4'],
            capture_output=True, text=True, timeout=120, cwd=tmpdir, env={**os.environ}
        )
        for root, dirs, files in os.walk(tmpdir):
            for f in files:
                if f.endswith('.mp4') and 'partial' not in root:
                    return {'path': os.path.join(root, f), 'title': f'{topic} - 教学动画'}
        return None
    except Exception as e:
        logger.warning("Manim render failed: %s", e)
        return None
