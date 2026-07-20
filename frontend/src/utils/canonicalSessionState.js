export function canonicalRequestKey(learnerId, subjectId) {
  return `${learnerId || ''}|${subjectId || ''}`;
}

export function canLoadCanonicalData(status, sessionId) {
  return status === 'resolved' && Boolean(sessionId);
}

export function acceptsCanonicalResult(activeKey, resultKey) {
  return activeKey === resultKey;
}

export function resolveActiveSubjectContext(activeSubject, activeClassSubject) {
  if (activeSubject?.id) {
    return {
      subjectId: activeSubject.id,
      subjectName: activeSubject.name || '',
      ...(activeSubject.textbookId ? { textbookId: activeSubject.textbookId } : {}),
    };
  }
  if (activeClassSubject?.subject) {
    return { subjectId: activeClassSubject.subject, subjectName: activeClassSubject.name || '' };
  }
  return {};
}

export function hydrateChatSessions(remoteSessions = [], cachedSessions = []) {
  const cachedById = new Map(cachedSessions.map((session) => [session.id, session]));
  return remoteSessions.map((session) => ({
    id: session.id,
    title: session.title || '未命名会话',
    messages: cachedById.get(session.id)?.messages || [],
    createdAt: Number(session.createdAt) || 0,
    updatedAt: Number(session.updatedAt) || 0,
  }));
}
