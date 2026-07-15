"""Regression checks for provider-unavailable ordinary chat."""

import asyncio

from app.services import deeptutor_client, langgraph_orchestrator as orchestrator
from app.services.conversation_state import ConversationState, ConversationStore
from app.services.profile_v2 import build_profile_v2


async def _no_reply(*_args, **_kwargs) -> str:
    return ""


async def _run(message: str, messages: list[dict], profile_v2: dict | None = None) -> dict:
    return await orchestrator.run_pipeline(
        user_message=message,
        messages=messages,
        profile_facts={},
        profile_v2=profile_v2 or {},
        session_id="chat-fallback-test",
    )


def main() -> None:
    original_chat = orchestrator.deeptutor.chat
    original_direct = deeptutor_client._direct_llm_fallback
    orchestrator.deeptutor.chat = _no_reply
    deeptutor_client._direct_llm_fallback = _no_reply
    try:
        greeting = asyncio.run(_run("你好", [{"role": "user", "content": "你好"}]))
        assert "你好！我是EduAgent" in greeting["final_reply"]
        assert greeting["current_message_is_greeting"] is True

        identity = asyncio.run(_run("我是大二学生", [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}, {"role": "user", "content": "我是大二学生"}]))
        assert "大二学生" in identity["final_reply"]
        assert "你好！我是EduAgent" not in identity["final_reply"]
        assert identity["fallback_used"] is True and identity["reply_source"] == "chat_fallback"

        preference = asyncio.run(_run("我喜欢通过视频学习", [{"role": "user", "content": "我喜欢通过视频学习"}]))
        assert "视频" in preference["final_reply"] and "你好！我是EduAgent" not in preference["final_reply"]

        temporary = asyncio.run(_run("我这次只想简单了解一下递归", [{"role": "user", "content": "我这次只想简单了解一下递归"}]))
        assert "临时偏好" in temporary["final_reply"]
        assert "你好！我是EduAgent" not in temporary["final_reply"]
        learning = asyncio.run(_run("我想学数据结构", [{"role": "user", "content": "我想学数据结构"}]))
        assert "数据结构" in learning["final_reply"] and learning["intent"] == "none"
        comparison = asyncio.run(_run("比较数组和链表的优缺点，不要生成学习路径，只回答这个问题", [{"role": "user", "content": "比较数组和链表的优缺点，不要生成学习路径，只回答这个问题"}]))
        assert "路径的基础概念" not in comparison["final_reply"]
        recap = asyncio.run(_run("请复述我刚才告诉你的身份信息，不要打招呼", [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}, {"role": "user", "content": "我是大二学生"}, {"role": "assistant", "content": "已记录。"}, {"role": "user", "content": "请复述我刚才告诉你的身份信息，不要打招呼"}]))
        assert "大二学生" in recap["final_reply"] and "你好！我是EduAgent" not in recap["final_reply"]
        empty_reply, empty_meta = orchestrator._chat_fallback_reply("", [])
        assert "没有收到" in empty_reply and empty_meta["current_message_is_empty"] is True
    finally:
        orchestrator.deeptutor.chat = original_chat
        deeptutor_client._direct_llm_fallback = original_direct

    profile_v2 = {
        "subject_context": {"background": "大二学生", "resource_preferences": ["视频"]},
        "fact_records": {
            "background": {"value": "大二学生", "fact_type": "explicit", "scope": "global", "status": "active"},
            "resource_preferences": {"value": ["视频"], "fact_type": "explicit", "scope": "global", "status": "active"},
        },
    }
    preference_reply = orchestrator._profile_query_reply("我更喜欢通过什么方式学习？", profile_v2, {})
    recap_reply = orchestrator._profile_query_reply("请告诉我你记住的年级和学习偏好", profile_v2, {})
    assert "视频" in preference_reply and "大二学生" in recap_reply and "视频" in recap_reply
    profile_v2["fact_records"]["resource_preferences"]["is_disabled_for_personalization"] = True
    assert "视频" not in orchestrator._profile_query_reply("我更喜欢通过什么方式学习？", profile_v2, {})
    assert not orchestrator._is_usable_chat_reply("我没有完全理解你的意思，可以再具体说明一下吗？", "我想学数据结构")

    async def _provider_reply(*_args, **_kwargs) -> str:
        return "可以先从数据结构的基础概念开始。"

    orchestrator.deeptutor.chat = _provider_reply
    try:
        provider = asyncio.run(_run("我想学数据结构", [{"role": "user", "content": "我想学数据结构"}]))
        assert provider["final_reply"] == "可以先从数据结构的基础概念开始。"
    finally:
        orchestrator.deeptutor.chat = original_chat

    orchestrator.deeptutor.chat = _no_reply
    deeptutor_client._direct_llm_fallback = _provider_reply
    try:
        provider = asyncio.run(_run("我想学数据结构", [{"role": "user", "content": "我想学数据结构"}]))
        assert provider["final_reply"] == "可以先从数据结构的基础概念开始。"
    finally:
        orchestrator.deeptutor.chat = original_chat
        deeptutor_client._direct_llm_fallback = original_direct

    store = ConversationStore()
    state = ConversationState(session_id="profile-fact-test")
    store.extract_facts(state, "我是大二学生")
    assert state.facts["background"] == "大二学生"
    profile = build_profile_v2(facts=state.facts, session_id=state.session_id)
    assert profile["fact_records"]["background"]["fact_type"] == "explicit"
    assert "视频" in build_profile_v2(facts={"preference": "视频/动画"})["subject_context"]["resource_preferences"]
    before = dict(state.facts)
    store.extract_facts(state, "我这次只想简单了解一下递归")
    assert state.facts == before
    print("chat fallback: PASS")


if __name__ == "__main__":
    main()
