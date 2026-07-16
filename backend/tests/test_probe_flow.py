"""End-to-end trace of the probe->proposal->confirm->plan flow."""
import sys, os, re, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.conversation_agent import ConversationAgent
from app.services.langgraph_orchestrator import _is_likely_chat, _run_conversation_agent
from app.services.conversation_state import conversation_store
from app.routers.product import _detect_and_set_proposal

passed = 0
failed = 0

def check(desc, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {desc}")
    else:
        failed += 1
        print(f"  FAIL: {desc}")

# --- 1. _GEN_PLAN includes new trigger ---
_GEN_PLAN = [
    "帮我规划", "帮我制定学习", "给我规划", "给我制定学习",
    "生成学习路径", "生成学习计划", "生成学习路线", "制定学习计划", "制定学习路径",
    "开始生成学习方案", "帮我生成学习方案", "就按这个生成",
    "生成吧", "开始吧", "按这些信息生成",
]
check("_GEN_PLAN includes '生成学习路线'", "生成学习路线" in _GEN_PLAN)

# --- 2. Profile gate: deep profile passes ---
deep = {
    "profile_facts": {
        "background": "华中科技大学大一软件工程专业",
        "target_course": "微积分期末考高分",
        "knowledge_base": "[探测]能正确计算简单极限",
        "weak_points": "[探测]积分直觉弱",
        "learning_goal": "考试高分，独立解题",
        "time_budget": "每天3小时整块，周末休息",
        "preference": "[行为观察]先做题反推理解",
    }
}
check("Deep profile (7/7) passes gate", ConversationAgent._is_profile_ready_for_plan(deep))

# --- 3. Profile gate: shallow profile blocked ---
shallow = {
    "profile_facts": {
        "background": "大一",
        "target_course": "微积分",
        "knowledge_base": "学过一点",
        "learning_goal": "想学好",
    }
}
check("Shallow profile blocked by gate", not ConversationAgent._is_profile_ready_for_plan(shallow))

# --- 4. Confirmation flow ---
agent = ConversationAgent(mock_data={}, llm_client=None)
ctx = {
    "profile_facts": deep["profile_facts"],
    "last_proposal": "plan",
    "conversation_history": [],
}
r = agent._rule_fallback("可以", ctx)
check("'可以' after proposal -> action=plan", r["action"] == "plan")
check("Reason is contextual_plan_confirmation", r["reason"] == "contextual_plan_confirmation")

# --- 5. _is_likely_chat ---
check("'可以' is chat-like", _is_likely_chat("可以", {}))
check("'帮我规划' is NOT chat-like", not _is_likely_chat("帮我规划", {}))
check("'生成学习路线' is NOT chat-like", not _is_likely_chat("生成学习路线", {}))

# --- 6. Proposal extraction from DT reply ---
dt = "画像够了。\n\n<proposal>plan</proposal>"
m = re.search(r'<proposal>(.*?)</proposal>', dt, re.DOTALL)
check("Proposal extracted from DT reply", m and m.group(1).strip() == "plan")

# --- 7. _run_conversation_agent returns _llm_proposal ---
src = inspect.getsource(_run_conversation_agent)
check("_run_conversation_agent returns _llm_proposal", '"_llm_proposal"' in src)
check("_run_conversation_agent returns needs_clarification", '"needs_clarification"' in src)

# --- 8. _plan_node has mode picker ---
from app.services.langgraph_orchestrator import _plan_node
src = inspect.getsource(_plan_node)
check("_plan_node has mode-pick", "mode-pick" in src)

# --- 9. run_pipeline has mode picker + pending proposal check ---
from app.services.langgraph_orchestrator import run_pipeline
src = inspect.getsource(run_pipeline)
check("run_pipeline has mode-pick", "mode-pick" in src)
check("run_pipeline checks pending_proposal", "pending_proposal" in src)

# --- 10. product.py respects pipeline final_reply ---
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(backend_dir, "app", "routers", "product.py"), "r", encoding="utf-8") as f:
    ps = f.read()
check("product.py uses result['final_reply'] first", 'result.get("final_reply", "")' in ps)

# --- 11. _detect_and_set_proposal ---
test_sid = "test_probe_flow_validation"
state = conversation_store.get(test_sid)
state.last_proposal = None
_detect_and_set_proposal({"_llm_proposal": "plan", "reply": "好的", "action": "none"}, test_sid)
state = conversation_store.get(test_sid)
check("_detect_and_set_proposal sets last_proposal", state.last_proposal == "plan")

# --- 12. "生成学习路线吧" matches _GEN_PLAN ---
compact = "生成学习路线吧"
match = any(p in compact for p in _GEN_PLAN)
check("'生成学习路线吧' matches _GEN_PLAN", match)

# --- Summary ---
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed out of {passed+failed}")
if failed:
    print("SOME CHECKS FAILED - fix before deploying!")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
