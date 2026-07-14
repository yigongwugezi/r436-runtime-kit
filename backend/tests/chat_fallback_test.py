"""Regression checks for provider-unavailable ordinary chat."""

import asyncio

from app.services import langgraph_orchestrator as orchestrator
from app.services.conversation_state import ConversationState, ConversationStore
from app.services.profile_v2 import build_profile_v2


async def _no_reply(*_args, **_kwargs) -> str:
    return ""


async def _run(message: str, messages: list[dict]) -> dict:
    return await orchestrator.run_pipeline(
        user_message=message,
        messages=messages,
        profile_facts={},
        session_id="chat-fallback-test",
    )


def main() -> None:
    original_chat = orchestrator.deeptutor.chat
    orchestrator.deeptutor.chat = _no_reply
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
        recap = asyncio.run(_run("请复述我刚才告诉你的身份信息，不要打招呼", [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}, {"role": "user", "content": "我是大二学生"}, {"role": "assistant", "content": "已记录。"}, {"role": "user", "content": "请复述我刚才告诉你的身份信息，不要打招呼"}]))
        assert "大二学生" in recap["final_reply"] and "你好！我是EduAgent" not in recap["final_reply"]
        empty_reply, empty_meta = orchestrator._chat_fallback_reply("", [])
        assert "没有收到" in empty_reply and empty_meta["current_message_is_empty"] is True
    finally:
        orchestrator.deeptutor.chat = original_chat

    store = ConversationStore()
    state = ConversationState(session_id="profile-fact-test")
    store.extract_facts(state, "我是大二学生")
    assert state.facts["background"] == "大二学生"
    profile = build_profile_v2(facts=state.facts, session_id=state.session_id)
    assert profile["fact_records"]["background"]["fact_type"] == "explicit"
    before = dict(state.facts)
    store.extract_facts(state, "我这次只想简单了解一下递归")
    assert state.facts == before
    print("chat fallback: PASS")


if __name__ == "__main__":
    main()
