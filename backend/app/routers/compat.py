"""Compatibility stubs for old product.py endpoints the frontend still calls."""

from fastapi import APIRouter

router = APIRouter(tags=["compat"])


@router.get("/api/chat/quick-commands")
def quick_commands() -> dict:
    return {"commands": [
        {"id": "1", "label": "生成学习方案", "icon": "Sparkles", "prompt": "帮我生成完整的个性化学习方案"},
        {"id": "2", "label": "诊断薄弱点", "icon": "Brain", "prompt": "帮我分析学习薄弱点"},
        {"id": "3", "label": "出练习题", "icon": "FileText", "prompt": "帮我出几道练习题"},
    ]}


@router.get("/api/chat/agents")
def list_agents() -> dict:
    return {"agents": [
        {"id": "profile", "name": "画像分析", "icon": "User", "description": "构建学习画像", "stage": "profiling"},
        {"id": "plan", "name": "路径规划", "icon": "Map", "description": "规划学习路径", "stage": "planning"},
        {"id": "resource", "name": "资源生成", "icon": "Book", "description": "生成学习资源", "stage": "generating"},
        {"id": "tutoring", "name": "智能辅导", "icon": "Bot", "description": "答疑解惑", "stage": "tutoring"},
        {"id": "grade", "name": "批改评估", "icon": "Check", "description": "批改作答", "stage": "reviewing"},
    ]}


@router.get("/api/chat/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    return {"messages": []}


@router.get("/api/learning-analytics")
def learning_analytics(sessionId: str = "", subjectId: str = "") -> dict:
    return {"totalStudyMinutes": 0, "completedTopics": [], "quizAccuracy": 0, "streak": 0, "lastStudyDate": 0}
