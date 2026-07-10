# 题目、小测、题集与判卷接口标准

## 端点总览

### 题目与判卷（原有）
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/questions/generate` | 生成题目 |
| GET | `/api/questions` | 查题目列表（不含答案） |
| GET | `/api/questions/{id}` | 单题详情 |
| POST | `/api/questions/{id}/grade` | 提交作答 + 判卷 |
| GET | `/api/questions/weak` | 错题本（支持 `?aggregate=true` 聚合） |
| GET | `/api/questions/history` | 答题历史 |

### 即时小测（Part 1-2 新增）
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/quizzes` | 创建小测 |
| GET | `/api/quizzes` | 列出小测 |
| GET | `/api/quizzes/{id}` | 获取小测及关联题目 |
| POST | `/api/quizzes/{id}/submit` | 提交作答 + 逐题评分 + 薄弱点回写 |
| GET | `/api/quizzes/{id}/results` | 查看小测结果（含答案和评分） |
| POST | `/api/quizzes/{id}/attempts` | 开始一次作答 |
| GET | `/api/quizzes/{id}/attempts` | 列出所有作答记录 |

### 小节即时生成（Part 2 新增）
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/sections/{section_id}/quiz/generate` | 从小节上下文 LLM 生成 3-5 题小测 |

### 大型题集（Part 4 新增）
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/exam-sets/generate` | LLM 生成题集（章节 10-12 / 阶段 15-18 / 路径 20-25 题） |
| POST | `/api/exam-sets` | 创建题集 |
| GET | `/api/exam-sets` | 列出题集（支持 scopeType/status 筛选） |
| GET | `/api/exam-sets/{id}` | 获取题集及关联题目 |
| PATCH | `/api/exam-sets/{id}` | 更新题集 |
| POST | `/api/exam-sets/{id}/submit` | 提交全部作答 + 评分 + 薄弱点回写 |
| GET | `/api/exam-sets/{id}/results` | 查看题集结果（含答案和评分） |
| POST | `/api/exam-sets/{id}/attempts` | 开始题集作答 |
| GET | `/api/exam-sets/{id}/attempts` | 列出题集所有作答记录 |

### 作答记录（Part 1 新增）
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/attempts` | 创建作答记录 |
| GET | `/api/attempts/{id}` | 获取作答记录及关联答案 |
| PATCH | `/api/attempts/{id}` | 更新作答（保存进度） |
| POST | `/api/attempts/{id}/submit` | 提交作答 |

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

---

## 新增数据结构（Part 1-5）

### Quiz（即时小测）
```json
{
  "id": "quiz_xxx", "title": "极限概念 小测", "sessionId": "session_xxx",
  "scopeType": "section", "scopeId": "sec_001",
  "pathId": null, "stageId": null, "chapterId": null, "sectionId": "sec_001",
  "knowledgePointIds": ["极限定义"], "difficulty": "medium", "questionCount": 4,
  "questions": [{"questionId": "q1", "type": "choice", "stemAbbr": "ε-δ定义"}],
  "linkedQuestions": [/* Question[] — 不含答案 */],
  "source": "llm_generated", "archivePolicy": "none", "createdAt": "2026-07-10T00:00:00Z"
}
```

### ExamSet（大型题集）
```json
{
  "id": "exam_xxx", "title": "第一章综合题集", "sessionId": "session_xxx",
  "scopeType": "chapter", "scopeId": "ch_01", "chapterId": "ch_01",
  "knowledgePointIds": ["AI概述", "图灵测试"], "difficulty": "medium",
  "difficultyDistribution": {"easy": 3, "medium": 5, "hard": 2},
  "questionCount": 10, "estimatedMinutes": 30, "totalScore": 100,
  "status": "not_started", "source": "llm_generated", "archivePolicy": "archive",
  "createdAt": "2026-07-10T00:00:00Z", "updatedAt": "2026-07-10T00:00:00Z"
}
```

### Attempt（作答记录）
```json
{
  "id": 1, "attemptId": "att_xxx", "sessionId": "session_xxx",
  "quizId": "quiz_xxx", "examSetId": null, "learnerId": "learner_xxx",
  "answers": [{"questionId": "q1", "studentAnswer": "B", "score": 100}],
  "totalScore": 85, "maxScore": 100, "status": "graded",
  "startedAt": "2026-07-10T00:00:00Z", "submittedAt": "2026-07-10T00:00:10Z"
}
```

### QuizResult（单题评分结果）
```json
{
  "questionId": "q1", "studentAnswer": "B", "isCorrect": true,
  "score": 100, "maxScore": 100, "correctAnswer": "B",
  "explanation": "极限的定义要求...", "feedback": "回答正确",
  "errorType": null, "errorLabel": null, "knowledgePoint": "极限定义"
}
```

### WeakPoint（薄弱知识点 — Part 3）
```json
{
  "name": "极限定义", "errorCount": 2, "totalAttempts": 3, "errorRate": 0.67,
  "lastErrorAt": "2026-07-10T00:00:00Z", "errorTypes": ["concept"],
  "masteryEstimate": 33, "suggestedAction": "建议重新学习极限定义",
  "source": "quiz_grading"
}
```

---

## 新增端点详情

### 7. 小节即时生成小测
`POST /api/sections/{section_id}/quiz/generate`
```json
// 请求: { sessionId, title, knowledgePoints[], lectureSummary, difficulty, pathId?, stageId?, chapterId?, sectionId? }
// 响应: { status, data: { quiz: Quiz, questions: [Question — 不含答案] } }
```
LLM 生成 3-5 题，题型混合选择/判断/简答。答案存储在服务端，提交后才返回。

### 8. 小测/题集提交与评分
`POST /api/quizzes/{quiz_id}/submit`
`POST /api/exam-sets/{exam_set_id}/submit`
```json
// 请求: { sessionId, answers: [{questionId, answer}] }
// 响应: { status, data: { attempt, results: [QuizResult], totalScore, maxScore,
//           sectionStatusSuggestion, weakPoints: [WeakPoint] } }
```
- 选择/判断：规则直接判定（100/0分）
- 简答：调用 GradingAgent LLM 评分
- 自动回写薄弱点到 ProfileSnapshotModel.weaknesses
- 状态建议：≥80% mastered, 50-79% in_progress, <50% needs_review

### 9. 题集 LLM 生成
`POST /api/exam-sets/generate`
```json
// 请求: { sessionId, title, scopeType, scopeId, knowledgePoints[], difficulty, questionCount? }
// 响应: { status, data: { examSet: ExamSet, questions: [Question — 不含答案] } }
```
题目数量按 scope_type 自动：chapter→12, stage→15, path→22。

### 10. 错题本聚合查询
`GET /api/questions/weak?sessionId=X&aggregate=true`
返回知识点级别薄弱汇总 `{weakPoints: [WeakPoint], total: N}`。

### 11. 新增数据库表

```sql
CREATE TABLE quizzes (
  id VARCHAR(64) PRIMARY KEY, title VARCHAR(256), session_id VARCHAR(64),
  scope_type VARCHAR(32), scope_id VARCHAR(64),
  path_id VARCHAR(64), stage_id VARCHAR(64), chapter_id VARCHAR(64), section_id VARCHAR(64),
  knowledge_point_ids JSON, difficulty VARCHAR(16), question_count INTEGER,
  questions JSON, source VARCHAR(32), archive_policy VARCHAR(16), created_at DATETIME
);
CREATE TABLE exam_sets ( /* 同上 + difficulty_distribution JSON, estimated_minutes INTEGER,
  total_score INTEGER, status VARCHAR(16), updated_at DATETIME */ );
CREATE TABLE attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id VARCHAR(64) UNIQUE,
  session_id VARCHAR(64), quiz_id VARCHAR(64), exam_set_id VARCHAR(64),
  answers JSON, total_score INTEGER, max_score INTEGER,
  status VARCHAR(16), learner_id VARCHAR(64),
  started_at DATETIME, submitted_at DATETIME, created_at DATETIME
);
ALTER TABLE answer_records ADD COLUMN attempt_id VARCHAR(64);
```
