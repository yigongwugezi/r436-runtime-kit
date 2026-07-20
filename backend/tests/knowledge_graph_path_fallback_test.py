"""Knowledge graph remains available without an LLM connection."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers import knowledge_graph
from app.routers.knowledge_graph import _path_kps


def main() -> None:
    rows = _path_kps([{
        "id": "stage-1", "title": "复杂度分析", "progressStatus": "current",
        "tasks": [
            {"id": "task-1", "title": "阅读讲义：渐进复杂度", "type": "read_doc", "status": "completed"},
            {"id": "task-2", "title": "练习测验：复杂度计算", "type": "quiz_prac", "status": "pending"},
        ],
    }])
    assert [row["id"] for row in rows] == ["stage-1", "task-1", "task-2"]
    assert rows[0]["_status"] == "in_progress" and rows[0]["_mastery"] == 50
    assert rows[1]["name"] == "渐进复杂度" and rows[1]["_status"] == "mastered"
    assert rows[2]["name"] == "复杂度计算" and rows[2]["part_of"] == "stage-1"
    assert rows[2]["prerequisites"] == ["task-1"]

    raw_path = {"stages": [
        {
            "stage_id": "stage-1", "title": "复杂度分析",
            "days": [{"tasks": [
                {"task_id": "task-1", "title": "阅读讲义：渐进复杂度", "status": "completed"},
                {"task_id": "task-2", "title": "练习测验：复杂度计算", "status": "pending"},
            ]}],
        },
        {
            "stage_id": "stage-2", "title": "线性表",
            "days": [{"tasks": [
                {"task_id": "task-3", "title": "阅读讲义：链表", "status": "pending"},
            ]}],
        },
    ]}
    with patch.object(knowledge_graph, "_resolve_session_id", return_value="session"), \
         patch.object(knowledge_graph, "_ensure_session_linked"), \
         patch.object(knowledge_graph, "ag_get_learning_path", return_value=raw_path), \
         patch.object(knowledge_graph, "ag_get_resources", return_value=[]), \
         patch.object(knowledge_graph, "_resolve_course_context", return_value=("", "")), \
         patch.object(knowledge_graph, "_generate_kps_via_llm", side_effect=AssertionError("LLM must not run")):
        graph = knowledge_graph.get_knowledge_graph(sessionId="session", subjectId="subject")
    assert [node["id"] for node in graph["data"]["nodes"]] == ["stage-1", "task-1", "task-2", "stage-2", "task-3"]
    print("knowledge graph path fallback: PASS")


if __name__ == "__main__":
    main()
