import { useChatStore } from '../store/chatStore';
import { useSubjectStore } from '../store/subjectStore';

/** 统一 Session Context Hook
 *
 * 提供当前会话的 sessionId、subjectId、sessions 列表，
 * 避免各组件重复从 store 读取。
 */
export function useSessionContext() {
  const sessionId = useChatStore((s) => s.currentSessionId);
  const sessions = useChatStore((s) => s.sessions);
  const setCurrentSession = useChatStore((s) => s.setCurrentSession);
  const newSession = useChatStore((s) => s.newSession);
  const currentSession = sessions.find((s) => s.id === sessionId);

  const subjectId = useSubjectStore((s) => s.activeSubject?.id);
  const activeSubject = useSubjectStore((s) => s.activeSubject);
  const subjects = useSubjectStore((s) => s.subjects);
  const setActiveSubject = useSubjectStore((s) => s.setActive);

  return {
    sessionId,
    sessions,
    currentSession,
    setCurrentSession,
    newSession,
    subjectId,
    activeSubject,
    subjects,
    setActiveSubject,
  };
}
