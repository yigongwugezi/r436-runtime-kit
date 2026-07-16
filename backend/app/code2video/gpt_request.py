"""API 请求层 — 统一走 llm_factory，不直接硬编码 provider。

保留此文件是为了 code2video/agent.py 的 import 兼容。
所有实际逻辑委托给 app.services.llm_factory。
"""

from app.services.llm_factory import get_planner, get_coder, get_critic

# Backward-compatible function aliases for agent.py
# get_planner() returns a callable with signature (prompt, max_tokens=..., max_retries=...)
request_deepseek_token = get_planner()
request_qwen_token = get_coder()
request_qwen_vl_frames = get_critic()
