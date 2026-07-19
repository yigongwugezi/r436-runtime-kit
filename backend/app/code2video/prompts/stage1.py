def get_prompt1_outline(knowledge_point, duration=5, reference_image_path=None, user_requirements=""):
    req_block = f"""
## 用户特殊要求（必须严格遵循，优先级最高）
{user_requirements}
""" if user_requirements else ""
    prompt = f"""你是一位优秀的教学设计专家。请为以下知识点设计一个内容充实、可直接用于动画制作的详细教学大纲。
{req_block}
知识点：{knowledge_point}

## 第一件事：判断知识类型（必须选一个）
- formula_derivation：数学/物理公式推导类（如导数、积分、牛顿第二定律）
- concept_principle：概念/原理讲解类（如光合作用、市场经济、勾股定理）
- process_flow：流程/步骤类（如血液循环、三羧酸循环、算法流程）
- history_event：历史事件/时间线类（如辛亥革命、工业革命）
- structure_anatomy：结构/组成类（如细胞结构、原子模型、电路组成）
- comparison：对比/辨析类（如有丝分裂vs减数分裂、古典vs凯恩斯）

## 第二件事：根据类型，每个 section 必须给出以下具体内容

【如果类型是 formula_derivation】
- 具体的函数表达式或公式（LaTeX 写法）
- 数值示例（至少2组不同参数的计算结果）
- 坐标范围、关键点坐标
- 动画分步（每步：画什么图形→显示什么公式→数值如何变化）

【如果类型是 concept_principle】
- 具体的输入/输出/因果关系（不要只说"展示过程"）
- 具体数值或比例（如果适用）
- 动画分步（每步：展示什么元素→标注什么文字→突出什么关系）

【如果类型是 process_flow】
- 流程每一步的具体名称和状态变化
- 元素在各步骤中的位置关系
- 动画分步（每步：谁变成谁→移动到哪→产生什么）

【如果类型是 history_event】
- 具体时间点、人物、地点
- 因果链：前因→事件→后果
- 动画分步（时间线上标记节点→展示因果箭头→关键数据）

【如果类型是 structure_anatomy】
- 各组成部分的具体名称和空间位置
- 各部分之间的连接/包含关系
- 动画分步（先展示整体→逐层展开→标注各部分）

【如果类型是 comparison】
- 对比双方的具体特征（至少各3条）
- 相同点和不同点的精确表述
- 动画分步（并列展示双方→逐条标注特征→高亮差异）

## 输出 JSON 格式
{{
    "topic": "具体主题名（不要泛化，要精准）",
    "knowledge_type": "从上面6个类型中选一个",
    "target_audience": "目标受众",
    "sections": [
        {{
            "id": "section_1",
            "title": "小节标题（要具体，如'f(x)=x²在x=1处的平均变化率计算'而不是'平均变化率'）",
            "content": "本小节要讲什么，必须包含具体的公式/名称/数值，禁止泛泛而谈",
            "example": "具体数值示例，至少包含计算过程或关键数据",
            "visual_elements": ["画面元素1（含颜色）", "画面元素2（含颜色）"],
            "animation_steps": [
                {{"step": 1, "action": "具体画什么/显示什么", "detail": "精确的公式或数值"}},
                {{"step": 2, "action": "接着做什么", "detail": "精确的公式或数值"}}
            ]
        }}
    ]
}}

## 严禁事项
- 禁止在 content 或 example 中出现"通过动画展示"、"引导学生理解"等教学用语——直接写要展示的具体内容
- 禁止用"某个函数"、"某个值"等模糊指代——必须有精确表达式
- 禁止 section 数量少于 3 个或多于 6 个
- 总时长参考：{duration} 分钟
"""
    return prompt
