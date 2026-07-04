"""Agent data proxy — 优先读 OpenClaw 缓存在 conversation_store 的结果，兜底查 Agent 服务"""
import json, logging, os
from pathlib import Path
import httpx
from fastapi import APIRouter
from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
load_dotenv(_env)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent-data", tags=["agent-data"])

DEEPTUTOR = "http://localhost:8000"
PROFILER = "http://localhost:8001"
GRADER = "http://localhost:8002"


def _try_parse_json(text: str) -> dict | None:
    """尝试从文本中提取 JSON——多重策略"""
    if not text: return None
    # 策略1: 整段JSON
    try: return json.loads(text)
    except: pass
    # 策略2: {} 包裹
    try:
        s = text.find("{"); e = text.rfind("}") + 1
        if s >= 0 and e > s: return json.loads(text[s:e])
    except: pass
    # 策略3: 去掉markdown代码块
    import re
    clean = re.sub(r'```(?:json)?\s*', '', text)
    clean = re.sub(r'```\s*', '', clean)
    try:
        s = clean.find("{"); e = clean.rfind("}") + 1
        if s >= 0 and e > s: return json.loads(clean[s:e])
    except: pass
    return None

def _extract_value(val) -> dict | str | None:
    """从 Agent 返回值中提取实际数据——处理 {'content': '...'} 嵌套"""
    if isinstance(val, str): return val
    if isinstance(val, dict):
        content = val.get("content", "")
        if isinstance(content, str) and content:
            parsed = _try_parse_json(content)
            return parsed if parsed else content
        return val
    return None

def _get_cached(session_id: str) -> dict:
    """从 conversation_store 读取 OpenClaw 缓存的最新结果"""
    try:
        from app.services.conversation_state import conversation_store
        state = conversation_store.get(session_id)
        last = getattr(state, 'last_result', None) or {}
        raw = last.get("openclaw_raw", "")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


@router.get("/profile/{student_id}")
def get_profile(student_id: str):
    # OpenClaw 缓存优先
    cached = _get_cached(student_id)
    profile = cached.get("profile") or cached.get("plan_reply", {}).get("profile")
    if isinstance(profile, dict) and profile.get("dimensions"):
        return profile
    # Socratic Profiler 兜底
    try:
        r = httpx.get(f"{PROFILER}/api/profile/{student_id}", timeout=10)
        if r.status_code == 200: return r.json()
        r = httpx.post(f"{PROFILER}/api/profile/analyze", json={"student_id": student_id}, timeout=30)
        if r.status_code == 200: return r.json()
    except Exception: pass
    return {"dimensions": {}}


@router.get("/learning-path/{student_id}")
def get_learning_path(student_id: str):
    # OpenClaw 缓存优先
    cached = _get_cached(student_id)
    for key in ("plan_reply", "profile", "diagnosis"):
        val = _extract_value(cached.get(key))
        if isinstance(val, dict):
            stages = val.get("stages") or val.get("learning_path") or []
            if stages: return {"stages": stages}
        elif isinstance(val, str):
            p = _try_parse_json(val)
            if p and p.get("stages"): return {"stages": p["stages"]}
    # DeepTutor 兜底
    try:
        r = httpx.get(f"{DEEPTUTOR}/api/v1/partners/eduagent/sessions", timeout=10)
        if r.status_code == 200:
            sessions = r.json()
            if sessions:
                sid = sessions[0].get("session_id") or sessions[0].get("id")
                if sid:
                    r = httpx.get(f"{DEEPTUTOR}/api/v1/partners/eduagent/sessions/{sid}", timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        meta = data.get("metadata", {}) or {}
                        return {"stages": meta.get("stages") or meta.get("learning_path") or []}
    except Exception: pass
    return {"stages": []}


@router.get("/resources/{student_id}")
def get_resources(student_id: str):
    # OpenClaw 缓存优先
    cached = _get_cached(student_id)
    for key in ("resources", "plan_reply"):
        val = _extract_value(cached.get(key))
        if isinstance(val, dict) and val.get("resources"):
            return {"resources": val["resources"]}
        elif isinstance(val, str):
            p = _try_parse_json(val)
            if p and p.get("resources"): return {"resources": p["resources"]}
    # DeepTutor 兜底
    try:
        r = httpx.get(f"{DEEPTUTOR}/api/v1/partners/eduagent/sessions", timeout=10)
        if r.status_code == 200:
            sessions = r.json()
            resources = []
            for sess in (sessions or [])[:3]:
                sid = sess.get("session_id") or sess.get("id")
                if not sid: continue
                r = httpx.get(f"{DEEPTUTOR}/api/v1/partners/eduagent/sessions/{sid}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    meta = data.get("metadata", {}) or {}
                    resources.extend(meta.get("resources", []))
            if resources: return {"resources": resources[:20]}
    except Exception: pass
    return {"resources": []}


@router.get("/questions/{student_id}")
def get_questions(student_id: str):
    # OpenClaw 缓存优先
    cached = _get_cached(student_id)
    for key in ("questions", "plan_reply"):
        val = _extract_value(cached.get(key))
        if isinstance(val, dict) and val.get("questions"):
            return {"questions": val["questions"]}
        elif isinstance(val, str):
            p = _try_parse_json(val)
            if p and p.get("questions"): return {"questions": p["questions"]}
    return {"questions": []}


@router.get("/analytics/{student_id}")
def get_analytics(student_id: str):
    # OpenClaw 缓存优先
    cached = _get_cached(student_id)
    grading = cached.get("grading")
    if isinstance(grading, dict) and grading.get("total_score") is not None:
        return {"total_questions": 1, "average_score": grading.get("total_score"), "error_distribution": {}, "weak_knowledge_points": []}
    # GRADE 兜底
    try:
        r = httpx.get(f"{GRADER}/api/grade/stats/{student_id}", timeout=10)
        if r.status_code == 200: return r.json()
    except: pass
    return {"total_questions": 0, "average_score": None, "error_distribution": {}, "weak_knowledge_points": []}
