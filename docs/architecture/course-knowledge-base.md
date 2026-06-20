# Runtime Kit 课程知识库规范

## 当前目标

项目不能只支持《人工智能导论》一门课。第一阶段先把课程知识库做成可扩展目录结构，后续新增课程时尽量只新增文件，不改业务代码。

## 目录结构

每门课程放在：

```text
knowledge_base/courses/{course_id}/
```

必需文件：

```text
course.json
outline.md
chapters/
```

示例：

```text
knowledge_base/courses/data_structures/
  course.json
  outline.md
  chapters/
    01-complexity.md
    02-linear-list.md
    03-stack-queue.md
```

## course.json 字段

```json
{
  "course_id": "data_structures",
  "course_name": "数据结构",
  "target_students": ["软件工程", "计算机类专业"],
  "difficulty": "introductory",
  "description": "课程简介",
  "chapters": [
    {
      "chapter_id": "01",
      "title": "章节标题",
      "file": "chapters/01-example.md",
      "difficulty": "easy",
      "prerequisites": ["先修知识"]
    }
  ]
}
```

## 后端接口

### 课程列表

`GET /api/courses`

自动扫描 `knowledge_base/courses/*/course.json`。

### 课程详情

`GET /api/courses/{course_id}`

返回课程元数据、章节列表和 `outline.md` 内容。

### 章节内容

`GET /api/courses/{course_id}/chapters/{chapter_id}`

返回某一章的 Markdown 内容。

## 对话中的课程匹配

后端已支持根据用户画像中的目标课程自动匹配课程库。例如：

- 用户说“想学习数据结构”，生成结果会使用 `data_structures`。
- 用户说“想入门人工智能”，生成结果会使用 `ai_intro`。
- 用户说“想复习栈和队列”，会根据章节标题和课程别名匹配到 `data_structures`。

注意：用户只是补充学习信息时，系统会先更新画像；只有用户明确说“开始生成学习方案”时，才启动完整工作流。

## 新增课程步骤

1. 在 `knowledge_base/courses/` 下新建课程目录。
2. 编写 `course.json`。
3. 编写 `outline.md`。
4. 在 `chapters/` 下添加章节 Markdown。
5. 运行测试：

```powershell
powershell -ExecutionPolicy Bypass -File backend\tests\run_conversation_tests.ps1
```

## 当前已有课程

- `ai_intro`: 人工智能导论
- `data_structures`: 数据结构

## 后续升级方向

1. 让智能体根据用户目标课程自动选择 `course_id`。
2. 用章节内容做 RAG 检索。
3. 为每门课配置知识图谱和题库。
4. 支持后台上传课程资料后自动生成 `course.json` 和章节文档。
