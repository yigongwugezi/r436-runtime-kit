export function createLectureEnsureGuard() {
  const unavailable = new Set();
  return {
    blocks: (scope) => unavailable.has(scope),
    recordError: (scope, status) => { if (status === 404) unavailable.add(scope); },
    retry: (scope) => unavailable.delete(scope),
  };
}
