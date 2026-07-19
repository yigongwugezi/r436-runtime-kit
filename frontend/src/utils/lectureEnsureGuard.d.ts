export function createLectureEnsureGuard(): {
  blocks(scope: string): boolean;
  recordError(scope: string, status: number): void;
  retry(scope: string): boolean;
};
