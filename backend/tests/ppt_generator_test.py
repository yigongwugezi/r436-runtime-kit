"""PPT generation uses a fake LLM and a disposable output directory."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("EDUAGENT_SKIP_ENV_FILE", "1")


class _FakeLLM:
    def chat(self, **_: object) -> str:
        return """# 二叉树层序遍历
- 使用队列按层访问节点，先访问根节点，再访问每一层从左到右的节点。
- 该方法适合展示树的层级结构，并能自然扩展为最短路径等问题。
---
# 遍历步骤
- 根节点入队；循环取出队首节点，访问它并让左右子节点依次入队。
- 队列为空时遍历结束，整个过程保证每个节点只会被访问一次。
---
# 小结
- 队列保存尚未处理的节点；先进先出保证按层访问。
- 时间复杂度为节点数，额外空间取决于树的最大宽度。"""


def main() -> None:
    from app.services.ppt_generator import generate_pptx

    with tempfile.TemporaryDirectory() as temp_dir:
        with patch("app.services.llm_client.get_llm_client", return_value=_FakeLLM()):
            with patch("app.services.ppt_generator.OUTPUT_DIR", Path(temp_dir)):
                generated = generate_pptx("二叉树层序遍历", session_id="ppt-test")
        assert generated
        output = Path(generated)
        assert output.exists() and output.stat().st_size > 0
        assert zipfile.is_zipfile(output)
    print("ppt generator: PASS")


if __name__ == "__main__":
    main()
