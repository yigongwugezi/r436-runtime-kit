import json
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.intent_agent import IntentAgent
from app.config import settings
from app.services.conversation_state import conversation_store
from app.services.course_catalog import course_catalog
from app.services.learning_tracker import learning_tracker
from app.services.llm_client import get_llm_client
from app.services.orchestrator import AgentOrchestrator


router = APIRouter(tags=["product"])

_last_result: dict[str, Any] | None = None
_bookmarks: set[str] = set()
_study_events: list[dict[str, Any]] = []


def _llm_client():
    return get_llm_client(settings.llm_provider)


def _classify_intent(message: str) -> dict[str, Any]:
    return IntentAgent(mock_data={}, llm_client=_llm_client()).classify(message)


def _run_agents(
    message: str = "我想学习人工智能导论",
    session_id: str = "frontend_session_001",
) -> dict[str, Any]:
    global _last_result
    state = conversation_store.get(session_id)
    agent_message = conversation_store.profile_prompt(state, latest_message=message)
    selected_course = course_catalog.match_course(
        state.facts.get("target_course") or message,
        default="ai_intro",
    )
    course_id = str((selected_course or {}).get("course_id") or "ai_intro")
    _last_result = AgentOrchestrator().run(
        session_id=session_id,
        course_id=course_id,
        user_message=agent_message,
    )
    if selected_course:
        _last_result["course"] = {
            "course_id": selected_course.get("course_id"),
            "course_name": selected_course.get("course_name"),
            "description": selected_course.get("description", ""),
            "chapter_count": selected_course.get("chapter_count", len(selected_course.get("chapters", []))),
        }
    conversation_store.set_result(session_id, _last_result)
    return _last_result


def _result(session_id: str = "frontend_session_001") -> dict[str, Any]:
    state = conversation_store.get(session_id)
    return state.last_result or _run_agents(session_id=session_id)


def _dimension_score(key: str, item: dict[str, Any]) -> int:
    value = str(item.get("value", ""))
    base = int(float(item.get("confidence", 0.75)) * 80)
    if any(word in value for word in ["弱", "薄弱", "不会", "没学过", "一般"]):
        return max(35, base - 20)
    if any(word in value for word in ["较好", "熟悉", "掌握", "可以", "基础"]):
        return min(90, base + 10)
    if key in {"learning_goal", "interests"}:
        return min(88, base + 8)
    return max(50, min(85, base))


def _to_profile(result: dict[str, Any]) -> dict[str, Any]:
    raw_profile = result.get("profile", {})
    dimensions = [
        {
            "key": key,
            "label": item.get("label", key),
            "value": _dimension_score(key, item),
            "confidence": item.get("confidence", 0.75),
            "description": item.get("value", ""),
            "updatedAt": int(time.time() * 1000),
        }
        for key, item in raw_profile.items()
    ]

    weak_points = result.get("diagnosis", {}).get("weak_knowledge_points", [])
    weaknesses = [
        {
            "topic": point.get("name", "待补齐知识点"),
            "mastery": 42 if point.get("priority") == "high" else 58,
            "priority": 9 if point.get("priority") == "high" else 6,
            "suggestedResources": ["res_lecture_001", "res_quiz_001"],
        }
        for point in weak_points
    ]

    return {
        "id": result.get("session_id", "frontend_session_001"),
        "nickname": "学习者",
        "createdAt": int(time.time() * 1000) - 86400000,
        "updatedAt": int(time.time() * 1000),
        "dimensions": dimensions,
        "weaknesses": weaknesses,
        "preferences": {
            "preferredFormats": ["text", "diagram", "code", "quiz"],
            "paceMinutes": 45,
            "difficulty": "beginner",
            "explainStyle": "diagram",
        },
        "history": {
            "totalStudyMinutes": learning_tracker.summary(result.get("session_id", "frontend_session_001"))[
                "totalStudyMinutes"
            ],
            "completedTopics": [],
            "quizAccuracy": 76,
            "streak": 3,
            "lastStudyDate": int(time.time() * 1000),
        },
    }


def _resource_type(resource_type: str) -> str:
    return "case_study" if resource_type == "practice" else resource_type


def _to_resource(item: dict[str, Any], course_id: str = "ai_intro") -> dict[str, Any]:
    content = item.get("content") or json.dumps(item.get("items", []), ensure_ascii=False, indent=2)
    resource_id = item.get("resource_id", "resource")
    return {
        "id": resource_id,
        "type": _resource_type(item.get("type", "lecture")),
        "title": item.get("title", "学习资源"),
        "description": item.get("description", ""),
        "content": content,
        "knowledgePoints": [item.get("related_stage_id", course_id)],
        "tags": [item.get("content_format", "markdown"), item.get("source", "mock")],
        "difficulty": "easy",
        "estimatedMinutes": 20,
        "format": "diagram" if item.get("type") == "mindmap" else "text",
        "mermaidDef": content if item.get("content_format") == "mermaid" else None,
        "createdAt": int(time.time() * 1000),
        "bookmarked": resource_id in _bookmarks,
        "studyStatus": "new",
    }


def _to_learning_path(result: dict[str, Any]) -> dict[str, Any]:
    course = result.get("course") or {}
    course_id = result.get("course_id", "ai_intro")
    course_name = course.get("course_name") or ("人工智能导论" if course_id == "ai_intro" else str(course_id))
    stages = []
    for index, stage in enumerate(result.get("learning_path", []), start=1):
        nodes = [
            {
                "id": f"{stage.get('stage_id', index)}_node_{node_index}",
                "topic": task,
                "description": stage.get("goal", ""),
                "prerequisites": [] if index == 1 else [f"stage_{index - 1}_node_1"],
                "mastery": 35 if index == 1 else 0,
                "status": "available" if index == 1 else "locked",
                "resources": [
                    {
                        "resourceId": f"res_{resource_type}_001",
                        "type": resource_type,
                        "title": resource_type,
                        "essential": node_index == 1,
                        "completed": False,
                    }
                    for resource_type in stage.get("resource_types", [])
                ],
                "isKeyPoint": node_index == 1,
            }
            for node_index, task in enumerate(stage.get("tasks", []), start=1)
        ]
        stages.append(
            {
                "id": stage.get("stage_id", f"stage_{index}"),
                "order": index,
                "title": stage.get("title", f"阶段 {index}"),
                "description": stage.get("duration", ""),
                "nodes": nodes,
                "objective": stage.get("goal", ""),
                "estimatedDays": 3,
            }
        )

    return {
        "id": f"path_{course_id}",
        "title": f"{course_name}个性化学习路径",
        "description": result.get("diagnosis", {}).get("recommended_strategy", ""),
        "courseName": course_name,
        "stages": stages,
        "createdAt": int(time.time() * 1000),
        "overallProgress": 18,
        "estimatedDays": 14,
    }


def _learning_plan_reply(result: dict[str, Any], intent: dict[str, Any]) -> str:
    profile = _to_profile(result)
    path = _to_learning_path(result)
    resources = [_to_resource(item, result.get("course_id", "ai_intro")) for item in result.get("resources", [])]
    weak = "、".join(item["topic"] for item in profile["weaknesses"][:3]) or "暂无明显短板"
    resource_names = "、".join(item["title"] for item in resources[:5])
    return (
        "## 个性化学习方案已生成\n\n"
        f"- 意图识别：{intent['intent']}，置信度 {intent['confidence']:.0%}\n"
        f"- 已构建 {len(profile['dimensions'])} 维学生画像\n"
        f"- 识别的重点薄弱点：{weak}\n"
        f"- 学习路径：{path['estimatedDays']} 天，{len(path['stages'])} 个阶段\n"
        f"- 已生成资源：{resource_names}\n\n"
        "你可以切换到「学习画像」「学习路径」和「资源库」页面查看完整结果。"
    )


def _casual_reply() -> str:
    return (
        "你好，我是 EduAgent。你可以告诉我你的专业、学习基础、目标和偏好的学习方式，"
        "我会帮你生成学习画像、学习路径和个性化资源。\n\n"
        "例如：我是软件工程大三学生，Python 和数据结构还可以，但线性代数比较弱，"
        "想用十天学懂神经网络，希望多给我代码实验和图解。"
    )


def _date_query_reply() -> str:
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"今天是 {now.year} 年 {now.month} 月 {now.day} 日，{weekdays[now.weekday()]}。"


def _clarification_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    if not state.messages:
        return "我刚刚没有足够上下文可以解释。你可以把不理解的那句话再发我一次。"

    known = "\n".join(conversation_store.known_lines(state)) or "- 暂时还没有稳定学习画像"
    questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=2))
    return (
        "我的意思是：我会先通过对话收集你的学习画像，再根据画像生成学习路径和资源。\n\n"
        f"当前我已记录：\n{known}\n\n"
        f"如果你想继续生成个性化学习方案，下一步最有用的是补充：\n{questions}"
    )


def _format_known_and_missing(session_id: str) -> tuple[str, list[dict[str, str]]]:
    state = conversation_store.get(session_id)
    known = "\n".join(conversation_store.known_lines(state))
    supplemental = "\n".join(conversation_store.supplemental_lines(state))
    if supplemental:
        known = f"{known}\n\n补充背景：\n{supplemental}" if known else f"补充背景：\n{supplemental}"
    missing = conversation_store.missing_fields(state, limit=4)
    return known, missing


def _readiness_line(session_id: str) -> str:
    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    return f"画像完整度：{readiness['filledCount']}/{readiness['totalCount']} 项"


def _info_request_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, missing = _format_known_and_missing(session_id)
    if not known:
        known = "- 暂时还没有稳定画像信息"

    if not missing:
        return (
            "你目前提供的信息已经够我生成第一版学习画像和学习路径了。\n\n"
            f"我已记录的信息：\n{known}\n\n"
            "下一步你可以直接说“开始生成学习方案”，或者继续补充最近做题情况、错题类型和喜欢的资源形式，我会继续更新画像。"
        )

    questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=2))
    return (
        "可以，我会根据你已经说过的信息继续补全画像，不需要一次性填表。\n\n"
        f"{_readiness_line(session_id)}\n\n我目前已记录：\n{known}\n\n"
        f"接下来最有用的是补充这几项：\n{questions}\n\n"
        "你可以直接用一句话回答，例如：我数据结构基础一般，链表和树比较薄弱，想两周内能做课程实验，更喜欢图解加代码。"
    )


def _profile_query_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    if state.last_result is None:
        known, missing = _format_known_and_missing(session_id)
        if known:
            questions = "\n".join(f"- {item['question']}" for item in missing[:3])
            return (
                "我现在已经能形成一个很粗的学习画像，但还不够完整。\n\n"
                f"已记录的信息：\n{known}\n\n"
                f"建议你继续补充：\n{questions}"
            )
        return (
            "我现在还没有足够信息判断你是什么类型的学习者。\n\n"
            "你可以告诉我你的专业、年级、学过什么、哪里薄弱、想达成什么目标。"
            "我会先构建学习画像，再基于画像回答你适合的学习方向和学习策略。"
        )

    profile = _to_profile(state.last_result)
    descriptions = [
        f"{dimension['label']}：{dimension['description']}"
        for dimension in profile["dimensions"]
        if dimension.get("description")
    ]
    summary = "\n".join(f"- {item}" for item in descriptions[:6])
    known, missing = _format_known_and_missing(session_id)
    missing_text = "\n".join(f"- {item['label']}" for item in missing[:3]) or "- 暂无明显缺失"
    return (
        "根据目前已有的学习画像，我对你的判断是：\n\n"
        f"{summary}\n\n"
        f"会话中额外记录的信息：\n{known or '- 暂无'}\n\n"
        f"后续还可以补充：\n{missing_text}\n\n"
        "这不是性格判断，而是基于你提供的学习背景、目标和偏好形成的学习画像。"
        "如果你补充更多学习经历或练习反馈，我可以继续更新这个判断。"
    )


def _profile_update_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, missing = _format_known_and_missing(session_id)
    updated = "\n".join(conversation_store.updated_lines(state))
    supplemental_updated = "\n".join(conversation_store.updated_supplemental_lines(state))
    update_text = "\n".join(part for part in [updated, supplemental_updated] if part) or "- 已记录你的补充信息"
    missing_questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=2))
    readiness = conversation_store.readiness(state)

    if readiness["readyToPlan"]:
        return (
            "收到，我已经把这条信息更新进你的学习画像了。\n\n"
            f"本次更新：\n{update_text}\n\n"
            f"{_readiness_line(session_id)}，已经可以生成第一版学习方案。\n\n"
            f"当前画像信息：\n{known}\n\n"
            "你可以继续补充薄弱点、学习时间或资源偏好；也可以直接说“开始生成学习方案”，我会启动多智能体生成学习路径和资源。"
        )

    if not updated and supplemental_updated:
        return (
            "收到，这条信息我会作为补充背景保留，但它还不足以决定学习路径。\n\n"
            f"本次记录：\n{supplemental_updated}\n\n"
            f"{_readiness_line(session_id)}\n\n"
            f"为了真正生成个性化学习方案，接下来更需要补充：\n{missing_questions}"
        )

    return (
        "收到，我已经把这条信息记进你的学习画像了。\n\n"
        f"本次更新：\n{update_text}\n\n"
        f"{_readiness_line(session_id)}\n\n当前已记录：\n{known or '- 暂时还没有稳定画像信息'}\n\n"
        f"为了更准确地规划，接下来建议你补充：\n{missing_questions}"
    )


def _start_advice_reply(session_id: str) -> str:
    state = conversation_store.get(session_id)
    known, _ = _format_known_and_missing(session_id)

    if not known and state.last_result is None:
        return (
            "如果你是第一次使用，我还不能直接判断你该从哪一步开始，因为我还没有你的学习画像。\n\n"
            "你先用一句话告诉我三个信息就够了：你是谁、想学什么、现在基础怎么样。\n"
            "例如：我是软件工程大三学生，Python 和数据结构还可以，线性代数比较弱，想用十天学懂神经网络。"
        )

    if state.last_result:
        path = state.last_result.get("learning_path", [])
        first_stage = path[0] if path else {}
        first_task = (first_stage.get("tasks") or ["先阅读入门讲义"])[0]
        stage_title = first_stage.get("title", "第一阶段")
        return (
            "我建议你从学习路径的第一步开始，而不是直接跳到练习或项目。\n\n"
            f"当前建议起点：{stage_title}\n"
            f"第一件事：{first_task}\n\n"
            "原因是这一步通常负责补齐概念框架，后面的题库、代码实验和拓展阅读才更容易吸收。"
            "你可以先去「学习路径」页面看第 1 阶段，再到「资源库」打开对应讲义。"
        )

    target = state.facts.get("target_course", "目标课程")
    weak = state.facts.get("weak_points") or state.facts.get("knowledge_base") or "当前薄弱基础"
    return (
        f"按你目前提供的信息，我建议先从「{target}」的基础概念层开始。\n\n"
        f"我已记录的信息：\n{known}\n\n"
        f"原因：你现在最需要先把「{weak}」对应的前置概念理顺，再进入练习和项目。\n"
        "如果你希望我给出完整路径，可以直接说“开始生成学习方案”。"
    )


def _learning_plan_request_reply(message: str, intent: dict[str, Any], session_id: str) -> tuple[str, bool]:
    state = conversation_store.get(session_id)
    readiness = conversation_store.readiness(state)
    if readiness["readyToPlan"]:
        return _learning_plan_reply(_run_agents(message, session_id=session_id), intent), True

    questions = "\n".join(f"- {question}" for question in conversation_store.next_questions(state, limit=3))
    known = "\n".join(conversation_store.known_lines(state)) or "- 暂时还没有稳定画像信息"
    return (
        "我可以生成学习方案，但现在画像信息还不够，直接生成容易不准。\n\n"
        f"{_readiness_line(session_id)}\n\n"
        f"当前已记录：\n{known}\n\n"
        f"请先补充这几项中的至少一两项：\n{questions}\n\n"
        "补充后你再说“开始生成学习方案”，我会启动多智能体协同生成画像、路径和资源。",
        False,
    )


def _tutoring_reply(message: str) -> str:
    return (
        "我理解你是在寻求知识点讲解或问题辅导。\n\n"
        f"你的问题是：{message}\n\n"
        "当前第一阶段还没有完整接入 TutorAgent，我可以先建议你补充："
        "课程名称、具体知识点、题目或代码片段。后续会由 KnowledgeAgent + TutorAgent "
        "给出文字解释、图解说明和练习建议。"
    )


def _resource_request_reply(message: str, session_id: str) -> str:
    result = _run_agents(message, session_id=session_id)
    resources = [_to_resource(item, result.get("course_id", "ai_intro")) for item in result.get("resources", [])]
    names = "、".join(item["title"] for item in resources[:5])
    return (
        "我识别到你在请求学习资源。\n\n"
        f"当前已为你准备这些资源：{names}\n\n"
        "可以到「资源库」页面查看。后续 ResourceAgent 会进一步接入大模型，按主题实时生成讲义、题库、思维导图和实操案例。"
    )


def _feedback_reply(message: str) -> str:
    learning_tracker.log({"event": "chat_feedback", "metadata": {"message": message}})
    return (
        "收到你的学习反馈了。我已经记录这次反馈，后续会用于调整画像、资源推荐和学习路径。\n\n"
        "第一阶段目前记录在内存事件里，下一步会升级为 SQLite 或 JSON 持久化。"
    )


def _unknown_reply(intent: dict[str, Any]) -> str:
    return (
        "我还不确定你这句话想让我做什么。\n\n"
        f"当前判断：{intent['intent']}，置信度 {intent['confidence']:.0%}。\n\n"
        "你可以说明你是想：规划学习路径、解释知识点、生成学习资源，还是反馈学习进度。"
    )


def _reply_for_intent(message: str, intent: dict[str, Any], session_id: str) -> tuple[str, bool]:
    name = intent["intent"]
    if name == "casual_chat":
        return _casual_reply(), False
    if name == "date_query":
        return _date_query_reply(), False
    if name == "clarification":
        return _clarification_reply(session_id), False
    if name == "info_request":
        return _info_request_reply(session_id), False
    if name == "profile_query":
        return _profile_query_reply(session_id), False
    if name == "profile_update":
        return _profile_update_reply(session_id), False
    if name == "start_advice":
        return _start_advice_reply(session_id), False
    if name == "learning_plan":
        return _learning_plan_request_reply(message, intent, session_id)
    if name == "resource_request":
        return _resource_request_reply(message, session_id), True
    if name == "tutoring":
        return _tutoring_reply(message), False
    if name == "progress_feedback":
        return _feedback_reply(message), False
    if name == "unsafe":
        return "这个请求可能不适合处理。你可以换成正常的学习问题或课程规划需求。", False
    return _unknown_reply(intent), False


@router.post("/chat/stream")
def stream_chat(payload: dict[str, Any]) -> StreamingResponse:
    message = str(payload.get("message", "我想学习人工智能导论"))
    session_id = str(payload.get("sessionId", "frontend_session_001"))
    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message)
    conversation_store.set_intent(session_id, intent)
    reply, ran_agents = _reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", reply)

    NL = "\n"

    def event_stream():
        if ran_agents:
            yield f"data: {json.dumps({'content': '正在启动多智能体协同流程...' + NL, 'done': False}, ensure_ascii=False)}{NL}{NL}"
        else:
            intent_line = f"意图识别：{intent['intent']}（{intent['confidence']:.0%}）{NL}{NL}"
            yield f"data: {json.dumps({'content': intent_line, 'done': False}, ensure_ascii=False)}{NL}{NL}"
        for chunk in reply.splitlines(keepends=True):
            yield f"data: {json.dumps({'content': chunk, 'done': False}, ensure_ascii=False)}{NL}{NL}"
        yield 'data: {"done":true}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat/send")
def send_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "我想学习人工智能导论"))
    session_id = str(payload.get("sessionId", "frontend_session_001"))
    conversation_store.append_message(session_id, "user", message)
    intent = _classify_intent(message)
    conversation_store.set_intent(session_id, intent)
    reply, _ = _reply_for_intent(message, intent, session_id)
    conversation_store.append_message(session_id, "assistant", reply)
    return {
        "sessionId": session_id,
        "reply": {
            "id": "assistant_msg_001",
            "role": "assistant",
            "content": reply,
            "timestamp": int(time.time() * 1000),
        },
    }


@router.get("/chat/sessions")
def list_sessions() -> dict[str, Any]:
    return {"sessions": []}


@router.post("/chat/sessions/{session_id}/reset")
def reset_session(session_id: str) -> dict[str, Any]:
    conversation_store.reset(session_id)
    return {"ok": True, "sessionId": session_id}


@router.get("/chat/quick-commands")
def quick_commands() -> dict[str, Any]:
    return {
        "commands": [
            {"id": "ai_intro", "label": "AI 入门", "icon": "AI", "prompt": "我是大二学生，想两周入门人工智能"},
            {"id": "nn", "label": "神经网络", "icon": "NN", "prompt": "我想重点学习神经网络，希望多给图解和代码"},
            {"id": "data_structures", "label": "数据结构", "icon": "DS", "prompt": "我是软件工程大二学生，想复习数据结构，为了考试通过"},
        ]
    }


@router.get("/chat/progress/{task_id}")
def generation_progress(task_id: str) -> dict[str, Any]:
    return {"progress": {"stage": "多智能体生成中", "progress": 100, "agentName": "EduAgent", "detail": task_id}}


@router.get("/profile")
def get_profile(sessionId: str = "frontend_session_001") -> dict[str, Any]:
    return {"profile": _to_profile(_result(sessionId))}


@router.post("/profile/build")
def build_profile(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("sessionId", "frontend_session_001"))
    message = str(payload.get("message", "我想学习人工智能导论"))
    conversation_store.append_message(session_id, "user", message)
    return {"profile": _to_profile(_run_agents(message, session_id=session_id))}


@router.patch("/profile")
def update_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profile = _to_profile(_result())
    profile.update(payload)
    return {"profile": profile}


@router.get("/resources")
def get_resources(sessionId: str = "frontend_session_001") -> dict[str, Any]:
    result = _result(sessionId)
    resources = [_to_resource(item, result.get("course_id", "ai_intro")) for item in result.get("resources", [])]
    return {"resources": resources, "total": len(resources), "page": 1}


@router.get("/resources/{resource_id}")
def get_resource(resource_id: str, sessionId: str = "frontend_session_001") -> dict[str, Any]:
    result = _result(sessionId)
    resources = [_to_resource(item, result.get("course_id", "ai_intro")) for item in result.get("resources", [])]
    return {"resource": next((item for item in resources if item["id"] == resource_id), resources[0])}


@router.post("/resources/{resource_id}/bookmark")
def bookmark_resource(resource_id: str) -> dict[str, Any]:
    if resource_id in _bookmarks:
        _bookmarks.remove(resource_id)
        return {"bookmarked": False}
    _bookmarks.add(resource_id)
    return {"bookmarked": True}


@router.post("/resources/generate")
def generate_resource(payload: dict[str, Any]) -> dict[str, Any]:
    result = _result(str(payload.get("sessionId", "frontend_session_001")))
    resources = [_to_resource(item, result.get("course_id", "ai_intro")) for item in result.get("resources", [])]
    return {"resource": resources[0] | {"title": f"{payload.get('topic', '主题')} 个性化资源"}}


@router.get("/resources/{resource_id}/knowledge-graph")
def resource_knowledge_graph(resource_id: str) -> dict[str, Any]:
    return {
        "mermaidDef": (
            "mindmap\n"
            "  root((人工智能导论))\n"
            "    机器学习基础\n"
            "    神经网络\n"
            "    自然语言处理\n"
            f"    资源 {resource_id}"
        )
    }


@router.get("/learning-path")
def get_learning_path(sessionId: str = "frontend_session_001") -> dict[str, Any]:
    return {"path": _to_learning_path(_result(sessionId))}


@router.post("/learning-path/generate")
def generate_learning_path(payload: dict[str, Any]) -> dict[str, Any]:
    return {"path": _to_learning_path(_result(str(payload.get("sessionId", "frontend_session_001"))))}


@router.patch("/learning-path/nodes/{node_id}")
def update_node_progress(node_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("sessionId", "frontend_session_001"))
    learning_tracker.log(
        {"event": "node_progress", "resourceId": node_id, "metadata": payload},
        session_id=session_id,
    )
    return {"ok": True}


@router.post("/feedback")
def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("sessionId", "frontend_session_001"))
    learning_tracker.log({"event": "feedback", **payload}, session_id=session_id)
    return {"ok": True}


@router.post("/feedback/event")
def log_study_event(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("sessionId", "frontend_session_001"))
    learning_tracker.log(payload, session_id=session_id)
    return {"ok": True}


@router.get("/learning-analytics")
def learning_analytics(sessionId: str = "frontend_session_001") -> dict[str, Any]:
    analytics = learning_tracker.summary(sessionId)
    return {
        **analytics,
        "summary": "已接入学习事件追踪，可用于后续动态调整画像、资源推荐和学习路径。",
    }
