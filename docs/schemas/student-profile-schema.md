# Student Profile Schema

## 1. Purpose

The student profile is used by EduAgent to understand the learner and generate personalized learning paths and resources.

Stage 1 must include 8 dimensions:

```text
major_background
knowledge_base
learning_goal
cognitive_style
weak_points
programming_ability
learning_progress
interests
```

## 2. Dimension Structure

Each profile dimension must use this structure:

```json
{
  "label": "专业背景",
  "value": "电子信息专业大二学生",
  "confidence": 0.95,
  "source": "user_input",
  "evidence": "我是电子信息专业大二学生"
}
```

Field meaning:

| Field | Meaning |
| --- | --- |
| `label` | Chinese display name used by frontend |
| `value` | Extracted or inferred student feature |
| `confidence` | Confidence score, from 0 to 1 |
| `source` | Source of the information |
| `evidence` | Text evidence or inference reason |

Allowed `source` values:

```text
user_input
inferred
diagnosis
feedback
```

## 3. Full Schema Example

```json
{
  "major_background": {
    "label": "专业背景",
    "value": "电子信息专业大二学生",
    "confidence": 0.95,
    "source": "user_input",
    "evidence": "我是电子信息专业大二学生"
  },
  "knowledge_base": {
    "label": "知识基础",
    "value": "Python 基础中等，机器学习基础薄弱",
    "confidence": 0.9,
    "source": "user_input",
    "evidence": "学过 Python，但机器学习基础比较薄弱"
  },
  "learning_goal": {
    "label": "学习目标",
    "value": "两周入门人工智能，重点理解神经网络和自然语言处理",
    "confidence": 0.95,
    "source": "user_input",
    "evidence": "想用两周时间入门人工智能"
  },
  "cognitive_style": {
    "label": "认知风格",
    "value": "偏好图解、代码案例和练习题",
    "confidence": 0.9,
    "source": "user_input",
    "evidence": "希望多给我一些图解、代码案例和练习题"
  },
  "weak_points": {
    "label": "易错点",
    "value": "机器学习概念、神经网络训练流程、NLP 基础概念",
    "confidence": 0.75,
    "source": "inferred",
    "evidence": "由知识基础和学习目标推断"
  },
  "programming_ability": {
    "label": "编程能力",
    "value": "具备 Python 基础，适合从可运行小案例入手",
    "confidence": 0.85,
    "source": "user_input",
    "evidence": "学过 Python"
  },
  "learning_progress": {
    "label": "学习进度",
    "value": "准备开始系统学习人工智能导论",
    "confidence": 0.75,
    "source": "inferred",
    "evidence": "希望两周入门"
  },
  "interests": {
    "label": "兴趣方向",
    "value": "神经网络、自然语言处理",
    "confidence": 0.95,
    "source": "user_input",
    "evidence": "重点理解神经网络和自然语言处理"
  }
}
```

## 4. Frontend Display Rules

- Display `label` as the card title.
- Display `value` as the main content.
- Display `confidence` as a progress bar or badge.
- Display `source` using different tag styles.
- `evidence` can be shown in a tooltip or detail area.

## 5. Backend Rules

- All 8 dimensions must exist in the response.
- If a dimension cannot be extracted directly, fill it using inference and set `source` to `inferred`.
- `confidence` must be between 0 and 1.
- Do not return mixed field names such as `learningGoal` or `major`; use the fixed snake_case names.

