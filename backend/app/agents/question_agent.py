"""
试题生成智能体 — 基于诊断结果和知识点信息，LLM 生成高质量练习题。
支持选择题/填空题/判断题/解答题/变式题，含自洽性检验。
"""

import json
import logging
import re
import time
import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.services.llm_client import LLMClientError
from app.utils.llm_json import parse_safe

logger = logging.getLogger(__name__)

QUESTION_TYPES = ["choice", "fill", "truefalse", "shortanswer", "variant"]
DIFFICULTY_LEVELS = {"easy": "简单", "medium": "中等", "hard": "困难"}


class QuestionAgent(BaseAgent):
    agent_id = "question_agent"
    agent_name = "试题生成智能体"

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """主入口"""
        diagnosis = context.get("diagnosis", {}) if isinstance(context.get("diagnosis"), dict) else {}
        profile = context.get("profile", {})
        profile_facts = context.get("profile_facts", {}) if isinstance(context.get("profile_facts"), dict) else {}
        knowledge_points = self._extract_knowledge_points(context, diagnosis)
        user_message = str(profile_facts.get("_raw_user_message", context.get("user_message", ""))).strip()

        if not knowledge_points:
            return {"questions": [], "limitations": ["未找到可用于出题的知识点。请先完成诊断或指定课程。"],
                    "agent_step": self.agent_step()}

        # 从用户消息解析出题参数
        params = self._parse_question_params(user_message)
        params["knowledge_points"] = knowledge_points[:10]

        # ── 按阶段分批出题，每个阶段独立题目集 ──
        all_questions = []
        stages = context.get("learning_path", []) or []
        batch_size = max(1, len(stages))
        stage_batches = [stages[i:i+1] for i in range(0, len(stages), 1)] if stages else [[]]

        for batch_stages in stage_batches:
            batch_kps = knowledge_points[:10]
            params["knowledge_points"] = batch_kps
            params["stage_title"] = batch_stages[0].get("title", "") if batch_stages else ""

            if self.llm_client:
                try:
                    questions = self._generate_with_llm(params, profile, context)
                    if questions:
                        # 每个批次独立 set_id
                        for q in questions:
                            q["question_set_id"] = self._make_set_id(context) + f"_{batch_kps[0].get('stage_id','s') if batch_kps else 'g'}"
                        all_questions.extend(questions)
                        continue
                except Exception as e:
                    logger.error("QuestionAgent batch failed: %s", e)

            # 规则兜底
            questions = self._build_rule_questions(params, profile)
            all_questions.extend(questions)

        return {"questions": all_questions, "question_set_id": self._make_set_id(context),
                "agent_step": self.agent_step()}

    def get_fallback(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"questions": [], "question_set_id": "",
                "limitations": ["试题生成智能体暂时不可用。"],
                "agent_step": {"agent_id": self.agent_id, "agent_name": self.agent_name,
                               "status": "failed", "summary": "QuestionAgent fell back to defaults.",
                               "source": "rule_based_fallback", "quality_status": "fallback"}}

    # ── 知识点提取 ──

    def _extract_knowledge_points(self, context: dict, diagnosis: dict) -> list[dict]:
        points = []
        # 1. 优先从学习路径阶段获取
        stages = context.get("learning_path", []) or []
        if not stages:
            # 从 profile_facts 推断
            facts = context.get("profile_facts", {})
            course = str(facts.get("target_course", ""))
            if course:
                points.append({"name": course, "reason": "学习目标"})
        for s in stages:
            if isinstance(s, dict) and s.get("title"):
                points.append({"name": str(s["title"]), "reason": "学习路径阶段", "priority": "medium",
                               "stage_id": s.get("stage_id", ""),
                               "tasks": s.get("tasks", [])})
        # 2. 从诊断结果补充
        for item in diagnosis.get("weak_knowledge_points", []) or []:
            if isinstance(item, dict) and item.get("name"):
                points.append({"name": str(item["name"]), "reason": str(item.get("reason", "")),
                               "priority": str(item.get("priority", "medium"))})
        # 3. 从课程章节补充
        course = context.get("course", {}) if isinstance(context.get("course"), dict) else {}
        for ch in course.get("chapters", [])[:5]:
            if isinstance(ch, dict) and ch.get("title"):
                points.append({"name": str(ch["title"]), "reason": "课程章节", "priority": "medium"})
        return points[:15]

    def _parse_question_params(self, message: str) -> dict:
        """从用户消息中解析出题参数。"""
        params = {"count": 10, "types": ["choice", "fill", "truefalse"], "difficulty": "medium"}
        # 数量
        num_match = re.search(r"(\d+)\s*(?:道|题|个)", message)
        if num_match:
            params["count"] = min(20, max(1, int(num_match.group(1))))
        # 题型
        if any(w in message for w in ["选择", "选项"]):
            params["types"] = ["choice"]
        elif any(w in message for w in ["填空"]):
            params["types"] = ["fill"]
        elif any(w in message for w in ["判断", "对错"]):
            params["types"] = ["truefalse"]
        elif any(w in message for w in ["解答", "简答", "大题"]):
            params["types"] = ["shortanswer"]
        elif any(w in message for w in ["变式", "换个", "类似"]):
            params["types"] = ["variant"]
        # 难度
        for key, label in DIFFICULTY_LEVELS.items():
            if label in message:
                params["difficulty"] = key
        return params

    # ── LLM 生成 ──

    def _generate_with_llm(self, params: dict, profile: dict, context: dict) -> list[dict] | None:
        points = params["knowledge_points"]
        points_text = "\n".join(
            f"- {p['name']}（优先级：{p.get('priority', 'medium')}）" for p in points[:8]
        )

        type_instructions = {
            "choice": "选择题：stem + options(4个选项数组) + correct(正确选项字母) + explanation + distractor_reasons(每个干扰项为何错，需包含对应的常见误区名称)",
            "fill": "填空题：stem(用___标记挖空处) + blanks(挖空处数量) + answers(正确答案数组) + explanation",
            "truefalse": "判断题：statement + correct(true/false) + misconception_explanation(为什么学生容易错，指出混淆的概念)",
            "shortanswer": "解答题：stem + reference_answer(完整解答) + scoring_rubric(分步评分标准数组) + step_hints(引导提示数组)",
            "variant": "变式题：基于已有题目，改变数字/情境/问法，保持考察同一知识点。包含：stem + original_question_id(原题ID) + variation_type(change_numbers|change_context|change_perspective) + correct + explanation",
        }
        types_text = "\n".join(type_instructions.get(t, "") for t in params["types"])

        prompt = f"""你是 EduAgent 的试题生成智能体。根据以下信息生成 {params['count']} 道{DIFFICULTY_LEVELS.get(params['difficulty'], '中等')}难度的练习题。

## 知识点范围
{points_text}

## 题型要求
{types_text}

## 规则
1. 题目必须紧扣给定知识点，不要编造不存在的概念
2. 选择题的干扰项要有迷惑性但明确错误
3. 每题解析分三步：先写解题思路和考点 → 再写分步推导 → 最后写明正确答案及为什么对。不要写"学生可能选错""常见错误"这种推测性内容——这是解析不是学情分析
4. 难度必须与 {DIFFICULTY_LEVELS.get(params['difficulty'], '中等')} 匹配
5. 题目之间不要重复，覆盖不同子知识点

## 输出格式
每道题包含：question_id, type, stem, difficulty, knowledge_points, tags
对应题型的专属字段。
只输出JSON：{{"questions": [...]}}"""

        try:
            raw = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": "你是专业的试题生成专家。每题解析必须写清楚：正确选项/答案、解题步骤、涉及的知识点、常见错误原因。只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            logger.info(f"QuestionAgent LLM raw response (first 300 chars): {raw[:300]}")
            parsed = parse_safe(raw)
            questions = parsed.get("questions") if isinstance(parsed, dict) else None
            if not isinstance(questions, list) or len(questions) == 0:
                logger.warning("QuestionAgent: parsed questions is empty or not a list")
                return None

            normalized = []
            generated_stems: list[str] = []  # 用于去重
            for idx, q in enumerate(questions[:params["count"]], 1):
                if not isinstance(q, dict):
                    continue
                nq = self._normalize_question(q, idx, params)
                if not nq:
                    logger.warning("Question %d dropped by normalization", idx)
                    continue

                nq["question_id"] = uuid.uuid4().hex[:12]

                # ── 自洽性检验（修复死代码：现在真的调用了）──
                if self.llm_client:
                    passed_consistency = self._self_consistency_check(nq)
                    if not passed_consistency:
                        logger.warning(f"Question {idx} failed self-consistency check, dropping")
                        continue  # 自洽失败 → 丢弃该题
                    nq["self_consistency_passed"] = True

                # ── 难度校准 ──
                if self.llm_client:
                    calibrated_diff = self._calibrate_difficulty(nq, params["difficulty"])
                    if calibrated_diff:
                        nq["difficulty"] = calibrated_diff

                # ── 去重检测（语义相似度）──
                stem = nq.get("stem", "")
                if self._is_duplicate(stem, generated_stems):
                    logger.warning(f"Question {idx} detected as duplicate, dropping")
                    continue
                generated_stems.append(stem)

                # 解析质量差 → 用 LLM 重写
                expl = nq.get("explanation", "") or ""
                bad_quality = len(expl) < 30 or "学生可能" in expl or "学生选择了" in expl
                if bad_quality and self.llm_client:
                    try:
                        nq["explanation"] = self._expand_explanation(nq)
                    except Exception:
                        pass
                normalized.append(nq)

            logger.info(f"QuestionAgent: generated {len(normalized)} questions (consistency+dedup filtered)")
            return normalized if len(normalized) >= 1 else None
        except Exception as e:
            logger.warning(f"QuestionAgent LLM generation failed: {e}")
            return None

    def _self_consistency_check(self, question: dict) -> bool:
        """让 LLM 自己解一遍题，检查答案是否一致。仅对选择题和判断题做。"""
        if question["type"] not in ("choice", "truefalse"):
            return True  # 填空和解答题不做自洽检验（太贵）
        if not self.llm_client:
            return True

        stem = question.get("stem", "")
        options = question.get("options", [])
        correct = question.get("correct", "")
        q_type = question["type"]

        checker_prompt = f"""请解答以下{'选择题' if q_type == 'choice' else '判断题'}，只输出答案。

题目：{stem}
{"选项：" + " ".join(f"{chr(65+i)}.{o}" for i, o in enumerate(options)) if options else ""}

对于{'选择题' if q_type == 'choice' else '判断题'}，请只输出{'选项字母' if q_type == 'choice' else 'true或false'}："""
        try:
            raw = self.llm_client.chat(
                messages=[{"role": "user", "content": checker_prompt}],
                temperature=0,
                max_tokens=20,
            )
            raw = raw.strip().lower()
            if q_type == "choice":
                return correct.lower() == raw[:1].lower()
            else:
                expected = "true" if correct is True or str(correct).lower() == "true" else "false"
                return expected in raw
        except Exception:
            return True  # 检验失败不阻塞

    def _calibrate_difficulty(self, question: dict, target_difficulty: str) -> str | None:
        """LLM 校验题目难度是否匹配目标难度。

        让 LLM 评估实际难度，如果不匹配则返回校准后的难度。
        """
        if not self.llm_client:
            return None
        target_label = DIFFICULTY_LEVELS.get(target_difficulty, "中等")
        stem = question.get("stem", "")[:300]
        q_type = question.get("type", "")
        try:
            raw = self.llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": f"评估这道{q_type}题的难度。题目：{stem}\n\n"
                               f"目标难度是{target_label}。请判断实际难度是 简单/中等/困难 中的哪个，只输出一个词。"
                }],
                temperature=0, max_tokens=10,
            )
            raw = raw.strip()
            for key, label in DIFFICULTY_LEVELS.items():
                if label in raw:
                    return key if key != target_difficulty else None
        except Exception:
            pass
        return None

    def _is_duplicate(self, stem: str, existing_stems: list[str]) -> bool:
        """去重检测：词级别 Jaccard 相似度 > 0.85 视为重复。

        备用方案：当 RAG embedder 可用时使用 embedding 余弦相似度。
        """
        if not existing_stems:
            return False
        # 快速词重叠检测
        import re as _re
        words_a = set(_re.findall(r'[一-鿿]+|[a-zA-Z]+', stem.lower()))
        if len(words_a) < 3:
            return False
        for existing in existing_stems[-20:]:  # 只检查最近20题
            words_b = set(_re.findall(r'[一-鿿]+|[a-zA-Z]+', existing.lower()))
            if not words_b:
                continue
            intersection = words_a & words_b
            union = words_a | words_b
            jaccard = len(intersection) / max(1, len(union))
            # 高重叠 + 长度相近 = 大概率重复
            len_ratio = min(len(stem), len(existing)) / max(1, max(len(stem), len(existing)))
            if jaccard > 0.85 and len_ratio > 0.6:
                return True
        return False

    def _maybe_flag_for_review(self, question: dict, params: dict) -> None:
        """高风险题目标记：涉及复杂计算或逻辑推理 → 加入人工审核队列。"""
        stem = str(question.get("stem", ""))
        risk_keywords = ["证明", "推导", "计算", "求解方程", "最优化", "积分", "差分", "级数"]
        is_high_risk = any(kw in stem for kw in risk_keywords)
        is_hard = question.get("difficulty") == "hard"
        if is_high_risk or is_hard:
            question["needs_review"] = True
            question["review_reason"] = "涉及复杂计算/逻辑" if is_high_risk else "高难度题目"

    def _normalize_question(self, item: dict, index: int, params: dict) -> dict | None:
        q_type = str(item.get("type", params["types"][0])).strip()
        if q_type not in QUESTION_TYPES:
            q_type = params["types"][0]  # fallback to requested type

        stem = str(item.get("stem", item.get("statement", ""))).strip()
        if not stem or len(stem) < 3:
            return None

        base = {
            "question_id": f"q_{index:03d}",
            "type": q_type,
            "stem": stem,
            "difficulty": str(item.get("difficulty", params["difficulty"])),
            "knowledge_points": item.get("knowledge_points", [p["name"] for p in params["knowledge_points"][:3]]),
            "tags": [q_type, params["difficulty"]],
            "explanation": str(item.get("explanation", "")),
            "source": "llm_generated",
            "quality_status": "passed",
        }

        if q_type == "choice":
            options = item.get("options", [])
            if isinstance(options, list) and len(options) >= 2:
                base["options"] = [str(o) for o in options[:6]]
                base["correct"] = str(item.get("correct", "")).strip()
                base["distractor_reasons"] = item.get("distractor_reasons", [])
            elif isinstance(options, list) and len(options) == 0:
                # LLM 可能把选项放在 stem 里了，做个假选项
                base["options"] = ["A. 正确", "B. 错误"]
                base["correct"] = "A"
                base["explanation"] = "题目格式不完整，建议重新生成。"

        elif q_type == "fill":
            blanks = max(1, int(item.get("blanks", 1) or 1))
            answers = item.get("answers", [])
            base["blanks"] = blanks
            base["answers"] = [str(a) for a in (answers[:blanks] if isinstance(answers, list) else [str(answers)])]

        elif q_type == "truefalse":
            correct = item.get("correct", False)
            if isinstance(correct, str):
                correct = correct.lower() in ("true", "对", "正确", "yes", "t")
            base["correct"] = bool(correct)
            base["misconception_explanation"] = str(item.get("misconception_explanation", ""))

        elif q_type == "shortanswer":
            base["reference_answer"] = str(item.get("reference_answer", ""))
            base["scoring_rubric"] = item.get("scoring_rubric", [])
            base["step_hints"] = item.get("step_hints", [])

        elif q_type == "variant":
            base["original_question_id"] = str(item.get("original_question_id", ""))
            base["variation_type"] = str(item.get("variation_type", "change_context"))
            # 变式题本质上是某种基础题型 + 变体标记，保留基础题型字段
            base_type = str(item.get("base_type", "shortanswer"))
            if base_type == "choice":
                base["options"] = [str(o) for o in (item.get("options", []) or [])[:6]]
                base["correct"] = str(item.get("correct", ""))
            elif base_type == "fill":
                base["blanks"] = max(1, int(item.get("blanks", 1) or 1))
                base["answers"] = [str(a) for a in (item.get("answers", []) or [])]
            base["tags"] = base.get("tags", []) + ["variant", item.get("variation_type", "change_context")]

        # ── 高风险标记 ──
        self._maybe_flag_for_review(base, params)

        return base

    # ── 规则兜底 ──

    def _build_rule_questions(self, params: dict, profile: dict) -> list[dict]:
        points = params["knowledge_points"]
        if not points:
            return []

        questions = []
        for i, point in enumerate(points[:params["count"]], 1):
            q_type = params["types"][i % len(params["types"])]
            name = point.get("name", f"知识点{i}")

            if q_type == "choice":
                questions.append({
                    "question_id": f"q_{uuid.uuid4().hex[:12]}", "type": "choice",
                    "stem": f"以下关于{name}的描述，正确的是？",
                    "options": [
                        f"A. {name}的核心定义是正确的使用方法",
                        f"B. {name}可以在不考虑边界条件的情况下使用",
                        f"C. {name}的主要限制仅体现在理论层面",
                        f"D. 以上说法都不正确",
                    ],
                    "correct": "D",
                    "explanation": f"规则兜底生成。{name}的正确理解需要结合实际上下文，建议通过LLM生成获得更精准的题目。",
                    "difficulty": params["difficulty"],
                    "knowledge_points": [name],
                    "tags": ["choice", params["difficulty"]],
                    "source": "rule_based_fallback",
                    "quality_status": "fallback",
                })

            elif q_type == "truefalse":
                questions.append({
                    "question_id": f"q_{uuid.uuid4().hex[:12]}", "type": "truefalse",
                    "statement": f"在{name}中，可以忽略前置知识的依赖关系。",
                    "correct": False,
                    "explanation": f"规则兜底生成。{name}通常依赖于前置知识的掌握。",
                    "misconception_explanation": "学生可能认为各知识点是孤立的，忽视了依赖关系。",
                    "difficulty": params["difficulty"],
                    "knowledge_points": [name],
                    "tags": ["truefalse", params["difficulty"]],
                    "source": "rule_based_fallback",
                    "quality_status": "fallback",
                })

            elif q_type == "fill":
                questions.append({
                    "question_id": f"q_{uuid.uuid4().hex[:12]}", "type": "fill",
                    "stem": f"{name}的核心概念中，___是最基础的前提假设。",
                    "blanks": 1,
                    "answers": ["基础知识"],
                    "explanation": f"规则兜底生成。建议通过LLM生成获得更精准的填空题目。",
                    "difficulty": params["difficulty"],
                    "knowledge_points": [name],
                    "tags": ["fill", params["difficulty"]],
                    "source": "rule_based_fallback",
                    "quality_status": "fallback",
                })

            else:  # shortanswer
                questions.append({
                    "question_id": f"q_{uuid.uuid4().hex[:12]}", "type": "shortanswer",
                    "stem": f"请阐述{name}的核心原理，并给出一个应用实例。",
                    "reference_answer": f"{name}的原理可从定义、推导和应用三方面展开。",
                    "scoring_rubric": [
                        {"criterion": "原理描述", "points": 40},
                        {"criterion": "推导过程", "points": 30},
                        {"criterion": "应用实例", "points": 30},
                    ],
                    "step_hints": ["先回顾定义", "再推导关键公式", "最后举例"],
                    "difficulty": params["difficulty"],
                    "knowledge_points": [name],
                    "tags": ["shortanswer", params["difficulty"]],
                    "source": "rule_based_fallback",
                    "quality_status": "fallback",
                })

        return questions

    def _expand_explanation(self, q: dict) -> str:
        """用 LLM 重写质量差的解析"""
        stem = q.get("stem", "")
        answer = q.get("correct", "") or str(q.get("answers", ""))
        qtype = q.get("type", "choice")
        prompt = f"""{qtype}题目：{stem}
正确答案：{answer}

写解析禁止以下内容：不要写"学生可能"、"学生选择了"、"常见错误"等学情推测——你不是在批改，你是在解析题目。直接写解法。
格式：
解：先说明这道题考什么、用哪个公式/定理 → 再分步推导得出答案 → 最后给结论。
只输出解析正文，不加任何标题。"""
        raw = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_tokens=500,
        )
        return raw.strip()

    def _make_set_id(self, context: dict) -> str:
        session_id = str(context.get("session_id", ""))
        return f"qs_{session_id}_{hash(str(context.get('user_message', ''))) % 10000:04d}"
