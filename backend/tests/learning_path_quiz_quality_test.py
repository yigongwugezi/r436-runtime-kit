"""Quality gate for deterministic learning-path quiz fallback."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.routers.assessment import _task_quiz_questions


def main():
    questions = _task_quiz_questions({"title": "复杂度练习测验", "knowledge_points": ["Big O", "时间复杂度"]}, "complexity")
    banned = ("最符合本任务的核心学习目标", "理解并应用", "跳过关键概念", "只记忆无关事实", "不进行任何验证")
    assert len(questions) == 5
    assert len({q["stem"].replace(" ", "") for q in questions}) == 5
    assert len({q["knowledge_points"][0] for q in questions}) >= 3
    assert len({q["correct"] for q in questions}) >= 2
    assert any(token in " ".join(q["stem"] for q in questions) for token in ("循环", "链表", "复杂度"))
    for q in questions:
        assert len(q["options"]) == 4 and q["correct"] in {option[0] for option in q["options"]}
        assert q["explanation"] and not any(word in " ".join([q["stem"], *q["options"]]) for word in banned)
    print("learning path quiz quality: PASS")


if __name__ == "__main__": main()
