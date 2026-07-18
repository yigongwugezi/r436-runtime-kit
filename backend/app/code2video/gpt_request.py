"""API 请求层 — 统一走 llm_factory，不直接硬编码 provider。

保留此文件是为了 code2video/agent.py 的 import 兼容。
所有实际逻辑委托给 app.services.llm_factory。

注意：凭据来自每用户配置，因此**不能在 import 时绑定**（那会把进程启动
时解析到的一份凭据固定给所有用户）——这里改为调用时才解析的惰性包装。
"""

from app.services.llm_factory import get_planner, get_coder, get_critic


# Backward-compatible function aliases for agent.py — lazy delegation so the
# per-user credential context is resolved at call time, not import time.
def request_deepseek_token(prompt, max_tokens: int = 8000, max_retries: int = 3, **kwargs):
    return get_planner()(prompt, max_tokens=max_tokens, max_retries=max_retries, **kwargs)


def request_qwen_token(prompt, max_tokens: int = 8000, max_retries: int = 3, **kwargs):
    return get_coder()(prompt, max_tokens=max_tokens, max_retries=max_retries, **kwargs)


def request_qwen_vl_frames(prompt, image_paths, max_tokens: int = 8000, max_retries: int = 3, **kwargs):
    return get_critic()(prompt, image_paths, max_tokens=max_tokens, max_retries=max_retries, **kwargs)
