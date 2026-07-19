export function createLectureEnsureGuard() {
  const unavailable = new Set();
  return {
    blocks: (scope) => unavailable.has(scope),
    recordError: (scope, status) => { if ([403, 404, 409].includes(status)) unavailable.add(scope); },
    retry: (scope) => unavailable.delete(scope),
  };
}
