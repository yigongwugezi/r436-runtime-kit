export function canonicalRequestKey(learnerId, subjectId) {
  return `${learnerId || ''}|${subjectId || ''}`;
}

export function canLoadCanonicalData(status, sessionId) {
  return status === 'resolved' && Boolean(sessionId);
}

export function acceptsCanonicalResult(activeKey, resultKey) {
  return activeKey === resultKey;
}
