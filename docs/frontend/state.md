# 前端状态说明

## 状态管理层

使用 **Zustand** 进行全局状态管理，共 3 个 Store：

### 1. `chatStore.ts` — 对话状态

```typescript
interface ChatState {
  currentSessionId: string;    // 当前会话 ID，全局唯一标识
  sessions: ChatSession[];     // 所有历史会话
  messages: ChatMessage[];     // 当前会话的消息列表
  dataVersion: number;         // 数据版本号（对话完成后 +1，触发其他页面刷新）
  streaming: boolean;          // 是否正在流式生成
  agentProgress: AgentProgress | null; // 多智能体管线进度

  // Actions
  newSession: () => void;
  setCurrentSession: (id: string) => void;
  addMessage: (msg: ChatMessage) => void;
  setStreaming: (v: boolean) => void;
  setAgentProgress: (p: AgentProgress | null) => void;
  clearMessages: () => void;
  removeSession: (id: string) => void;
}
```

**传递方式**: 通过 Zustand 的 `useChatStore` 在组件间共享。所有页面通过 `currentSessionId` 发起 API 请求。

### 2. `subjectStore.ts` — 科目状态

```typescript
interface SubjectState {
  subjects: Subject[];          // 所有科目
  activeSubject: Subject | null; // 当前激活的科目

  // Actions
  create: (name: string) => Subject;
  setActive: (subject: Subject) => void;
  remove: (id: string) => void;
}
```

**传递方式**: Zustand store。科目切换后，`activeSubject.id` 作为 `subjectId` 参数传递给所有 API 请求。

### 3. `profileStore.ts` — 画像缓存

```typescript
interface ProfileState {
  profiles: Record<string, StudentProfile>; // subjectId → Profile
  setProfile: (subjectId: string, profile: StudentProfile) => void;
  clearProfile: (subjectId: string) => void;
}
```

**用途**: 缓存已加载的画像数据，避免重复请求。

## 页面状态传递

### sessionId 的传递
1. `chatStore.currentSessionId` 作为全局唯一会话标识
2. 所有 API 请求均携带此 ID（通过 `useChatStore.getState().currentSessionId`）
3. 登录时自动生成，保存在 `localStorage` 中

### subjectId 的传递
1. `subjectStore.activeSubject.id` 作为当前科目标识
2. 所有需要科目上下文的 API 携带此参数
3. 首页切换科目后，其他页面自动刷新

### 页面间数据刷新机制
- `chatStore.dataVersion` 在对话完成后递增
- 各页面 Hook（如 `useLearningAnalytics`）监听 `dataVersion`，变化时自动重新获取数据
- 科目切换时也触发各页面 Hook 的重新获取

### 本地存储 (localStorage)
| Key | 内容 |
|-----|------|
| `r436_runtime_learners` | 所有学习者列表 |
| `r436_runtime_active_learner` | 当前激活的学习者 |
| `r436_runtime_current_session_id` | 当前会话 ID |
| `r436_runtime_learning_prefs` | 学习偏好设置 |
| `r436_runtime_chat_history` | 对话历史缓存 |

## 页面状态枚举

每个页面统一使用 `PageStateType`:
```typescript
type PageStateType = 'loading' | 'empty' | 'error' | 'fallback' | 'generated' | 'idle';
```

对应展示组件：
- `loading` → `PageLoading`
- `empty` → `PageEmpty`
- `error` → `PageError`
- `fallback` → `FallbackBanner`
- `generated` → 正式内容（含 `SourceTag` 标记来源）
