"""Utility functions for Code2Video — extracted and adapted from showlab/Code2Video."""

import os
import re
import json
from pathlib import Path
from typing import List, Optional


def extract_json_from_markdown(text):
    """Extract JSON from markdown code blocks."""
    match = re.search(r"```(?:json)?\s*([{\[].*?[}\]])\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def extract_answer_from_response(response):
    """Extract text answer from various response formats."""
    try:
        content = response.candidates[0].content.parts[0].text
    except Exception:
        try:
            content = response.choices[0].message.content
        except Exception:
            content = str(response)
    return extract_json_from_markdown(content)


def replace_base_class(code: str, new_class_def: str) -> str:
    """Replace TeachingScene base class definition in generated code."""
    lines = code.splitlines(keepends=True)
    class_start = None

    for i, line in enumerate(lines):
        if re.match(r"^\s*class\s+TeachingScene\s*\(Scene\)\s*:", line):
            class_start = i
            break

    if class_start is not None:
        base_indent = len(lines[class_start]) - len(lines[class_start].lstrip())
        class_end = class_start + 1
        while class_end < len(lines):
            line = lines[class_end]
            if line.strip() != "" and (len(line) - len(line.lstrip()) <= base_indent):
                break
            class_end += 1

        new_block = new_class_def.strip() + "\n\n"
        return "".join(lines[:class_start]) + new_block + "".join(lines[class_end:])
    else:
        # Insert before first class definition
        for i, line in enumerate(lines):
            if re.match(r"^\s*class\s+\w+", line):
                return "".join(lines[:i]) + new_class_def.strip() + "\n\n" + "".join(lines[i:])
        return new_class_def.strip() + "\n\n" + "".join(lines)

    return code


def topic_to_safe_name(knowledge_point: str) -> str:
    """Convert topic name to safe filename."""
    SAFE_PATTERN = r"[^A-Za-z0-9 _\-\{\}\[\]\+&=\u03C0]"
    safe_name = re.sub(SAFE_PATTERN, "", knowledge_point)
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    return safe_name


def get_output_dir(idx: int, knowledge_point: str, base_dir, get_safe_name: bool = False):
    """Generate output directory for a knowledge point."""
    safe_name = topic_to_safe_name(knowledge_point)
    folder_name = f"{idx}-{safe_name}"

    if get_safe_name:
        return Path(base_dir) / folder_name, safe_name
    return Path(base_dir) / folder_name


def extract_video_frames(video_path: str, output_dir: Path, num_frames: int = 3) -> List[str]:
    """Extract key frames from video using FFmpeg for Critic evaluation.

    Returns list of frame image paths.
    """
    import subprocess
    import shutil as _shutil

    ffmpeg = _shutil.which("ffmpeg")
    if not ffmpeg:
        # Try common Windows locations
        for candidate in [
            r"C:\Users\hejiaxuan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe",
        ]:
            if os.path.isfile(candidate):
                ffmpeg = candidate
                break

    if not ffmpeg:
        return []

    # Get video duration
    try:
        result = subprocess.run(
            [str(ffmpeg), "-i", video_path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=15
        )
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        if duration_match:
            duration = int(duration_match.group(1))*3600 + int(duration_match.group(2))*60 + float(duration_match.group(3))
        else:
            duration = 10.0  # default
    except Exception:
        duration = 10.0

    frame_paths = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for i in range(num_frames):
        t = duration * (i + 1) / (num_frames + 1)  # evenly spaced
        frame_path = str(output_dir / f"frame_{i+1:02d}.png")
        try:
            subprocess.run(
                [str(ffmpeg), "-y", "-ss", str(t), "-i", video_path,
                 "-vframes", "1", "-q:v", "2", frame_path],
                capture_output=True, text=True, timeout=15
            )
            if os.path.isfile(frame_path):
                frame_paths.append(frame_path)
        except Exception:
            pass

    return frame_paths
