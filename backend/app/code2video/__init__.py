"""Code2Video module — adapted from showlab/Code2Video (ICML 2026).

Provides:
- TeachingVideoAgent: main video generation pipeline
- GPTRequest: API abstraction for DeepSeek/Qwen
"""
from .agent import TeachingVideoAgent, RunConfig

__all__ = ["TeachingVideoAgent", "RunConfig"]
