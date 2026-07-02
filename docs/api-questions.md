# 题目与判卷接口标准

## 端点总览

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/questions/generate` | 生成题目 |
| GET | `/api/questions` | 查题目列表（不含答案） |
| GET | `/api/questions/{id}` | 单题详情 |
| POST | `/api/questions/{id}/grade` | 提交作答 + 判卷 |
| GET | `/api/questions/weak` | 错题本 |
| GET | `/api/questions/history` | 答题历史 |

---

## 1. 生成题目

```
POST /api/questions/generate
```

**请求体**
```json
{
  "sessionId": "session_xxx",
  "message": "生成5道极限的选择题"
}
```

**响应**
```json
{
  "status": "success",
  "data": {
    "questionSetId": "qs_xxx",
    "questions": [ /* Question[] */ ],
    "count": 5
  }
}
```

---

## 2. 查题目列表

```
GET /api/questions?sessionId=xxx&knowledgePoint=极限&difficulty=medium&type=choice
```

**参数（均可选）**
| 参数 | 说明 |
|------|------|
| sessionId | 会话 ID |
| knowledgePoint | 按知识点过滤 |
| difficulty | easy / medium / hard |
| type | choice / fill / truefalse / shortanswer |

**响应**
```json
{
  "status": "success",
  "data": {
    "questionSetId": "qs_xxx",
    "questions": [ /* Question[]，不含答案 */ ],
    "count": 5
  }
}
```

> 列表接口默认**不返回答案字段**：`correct`、`answers`、`reference_answer`、`explanation`、`scoring_rubric`、`step_hints`

---

## 3. 单题详情

```
GET /api/questions/{question_id}?sessionId=xxx&reveal=false
```

| 参数 | 说明 |
|------|------|
| reveal | false = 不含答案（默认）；true = 含完整答案解析 |

**响应**
```json
{
  "status": "success",
  "data": {
    "question": { /* Question */ }
  }
}
```

---

## 4. 提交作答 / 判卷

```
POST /api/questions/{question_id}/grade
```

**请求体**
```json
{
  "sessionId": "session_xxx",
  "answer": "A"
}
```

**响应**
```json
{
  "status": "success",
  "data": {
    "gradingResult": {
      "question_id": "q_001",
      "student_answer": "A",
      "total_score": 85,
      "dimension_scores": {
        "reasoning": 90,
        "completeness": 80,
        "calculation": 85,
        "expression": 85
      },
      "dimension_feedback": {
        "reasoning": "解题方向正确",
        "completeness": "中间步骤略有跳跃",
        "calculation": "数值正确",
        "expression": "格式较规范"
      },
      "error_type": "null",
      "error_label": "无",
      "error_explanation": "",
      "error_action": "",
      "suggestions": ["可以补充中间推导步骤"],
      "strengths": ["整体思路清晰"]
    }
  }
}
```

---

## 5. 错题本

```
GET /api/questions/weak?sessionId=xxx&errorType=concept&limit=20
```

| 参数 | 说明 |
|------|------|
| errorType | concept / calculation / misreading / method / forgetting，不传=全部 |
| limit | 最大返回条数，默认 20 |

**响应**
```json
{
  "status": "success",
  "data": {
    "records": [
      {
        "question": { /* Question */ },
        "last_answer": "B",
        "grading_result": { /* GradingResult */ },
        "attempted_at": 1720000000000
      }
    ],
    "total": 12
  }
}
```

---

## 6. 答题历史

```
GET /api/questions/history?sessionId=xxx&limit=50
```

**响应**
```json
{
  "status": "success",
  "data": {
    "records": [
      {
        "question_id": "q_001",
        "question": { /* Question */ },
        "answer": "A",
        "grading_result": { /* GradingResult */ },
        "created_at": 1720000000000
      }
    ],
    "totalCorrect": 18,
    "totalAttempted": 25
  }
}
```

---

## 数据结构

### Question

```json
{
  "id": 1,
  "question_id": "q_001",
  "question_set_id": "qs_xxx",
  "session_id": "session_xxx",
  "type": "choice",
  "stem": "以下关于极限的描述，正确的是？",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "correct": "A",
  "explanation": "极限的定义要求...",
  "difficulty": "medium",
  "knowledge_points": ["极限", "连续"],
  "tags": ["choice", "medium"],
  "scoring_rubric": null,
  "reference_answer": null,
  "source": "llm_generated",
  "quality_status": "passed",
  "created_at": "2026-07-03T00:00:00Z"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| question_id | string | 题目唯一标识 |
| type | string | choice / fill / truefalse / shortanswer |
| stem | string | 题干 |
| options | json | 选择题选项数组 |
| correct | string | 正确答案（选择题=字母，判断题=true/false） |
| explanation | string | 解析 |
| difficulty | string | easy / medium / hard |
| knowledge_points | json | 关联知识点 |
| tags | json | 标签 |
| scoring_rubric | json | 解答题评分标准（可选） |
| reference_answer | string | 解答题参考答案（可选） |
| source | string | llm_generated / rule_based_fallback |
| quality_status | string | passed / warning / fallback |

### AnswerRecord

```json
{
  "id": 1,
  "session_id": "session_xxx",
  "question_id": "q_001",
  "student_answer": "A",
  "total_score": 85,
  "dimension_scores": { "reasoning": 90, "completeness": 80, "calculation": 85, "expression": 85 },
  "dimension_feedback": { "reasoning": "...", "completeness": "...", "calculation": "...", "expression": "..." },
  "error_type": "null",
  "error_label": "无",
  "error_explanation": "",
  "error_action": "",
  "suggestions": ["..."],
  "strengths": ["..."],
  "source": "llm_generated",
  "created_at": "2026-07-03T00:00:00Z"
}
```

### GradingResult（判卷结果，嵌入 AnswerRecord）

| 字段 | 类型 | 说明 |
|------|------|------|
| total_score | int | 0-100 |
| dimension_scores | json | `{reasoning, completeness, calculation, expression}` |
| dimension_feedback | json | 逐维度文字点评 |
| error_type | string | concept / calculation / misreading / method / forgetting / null |
| error_label | string | 中文标签 |
| error_explanation | string | 错误原因 |
| error_action | string | 建议处理动作 |
| suggestions | json | 改进建议数组 |
| strengths | json | 优点数组 |

---

## 错误类型

| error_type | 中文标签 | 处理动作 |
|-----------|---------|---------|
| concept | 概念错误 | 推送对应概念讲解，回溯前置知识 |
| calculation | 计算失误 | 提示验算方法，建议同类计算练习 |
| misreading | 审题不清 | 标注关键词训练 |
| method | 方法不当 | 推荐更优解法 |
| forgetting | 知识遗忘 | 加入艾宾浩斯复习队列 |
| null | 无 | 回答正确 |

---

## 数据库表

### questions
```sql
CREATE TABLE questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id TEXT NOT NULL UNIQUE,
  question_set_id TEXT,
  session_id TEXT NOT NULL,
  type TEXT NOT NULL,
  stem TEXT NOT NULL,
  options TEXT,
  correct TEXT,
  explanation TEXT,
  difficulty TEXT DEFAULT 'medium',
  knowledge_points TEXT,
  tags TEXT,
  scoring_rubric TEXT,
  reference_answer TEXT,
  source TEXT DEFAULT 'llm_generated',
  quality_status TEXT DEFAULT 'passed',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### answer_records
```sql
CREATE TABLE answer_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  student_answer TEXT NOT NULL,
  total_score INTEGER,
  dimension_scores TEXT,
  dimension_feedback TEXT,
  error_type TEXT,
  error_label TEXT,
  error_explanation TEXT,
  error_action TEXT,
  suggestions TEXT,
  strengths TEXT,
  source TEXT DEFAULT 'llm_generated',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
