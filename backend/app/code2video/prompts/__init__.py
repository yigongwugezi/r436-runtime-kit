# prompts/__init__.py
from .base_class import base_class
from .stage1 import get_prompt1_outline
from .stage2 import get_prompt2_storyboard, get_prompt_download_assets, get_prompt_place_assets
from .stage3 import get_prompt3_code, get_regenerate_note
from .stage4 import get_feedback_improve_code, get_feedback_list_prefix, get_prompt4_layout_feedback
from .stage5_eva import get_prompt_aes

__all__ = [
    "base_class",
    "get_prompt1_outline",
    "get_prompt2_storyboard",
    "get_prompt_download_assets",
    "get_prompt_place_assets",
    "get_prompt3_code",
    "get_feedback_list_prefix",
    "get_feedback_improve_code",
    "get_regenerate_note",
    "get_prompt4_layout_feedback",
    "get_prompt_aes",
]
