export type VideoRecommendationScope = {
  sessionId?: string;
  subjectId?: string;
  pathId?: string;
  stageId?: string;
  dayId?: string;
  globalDayIndex?: number;
  taskId?: string;
};

type VideoRecommendationResult = { resources: any[]; status: string; presentationStatus?: string };

const requests = new Map<string, Promise<VideoRecommendationResult>>();

export function videoRecommendationScope(scope: VideoRecommendationScope): string {
  const values = [scope.sessionId, scope.subjectId, scope.pathId, scope.stageId, scope.dayId, scope.globalDayIndex, scope.taskId, 'video'];
  return values.every((value) => value !== undefined && value !== null && value !== '') ? values.join('|') : '';
}

export function normalizeVideoRecommendations(body: any): VideoRecommendationResult {
  const data = body?.data ?? body ?? {};
  const recommendations = data.recommendations;
  const candidates = [recommendations?.resources, data.items, data.resources, recommendations, body?.items, body?.resources]
    .find(Array.isArray) ?? [];
  const resources = candidates.filter((item: any) => (item?.resource_type || item?.resourceType) === 'video');
  const presentationStatus = recommendations?.presentationStatus;
  return { resources, status: String(recommendations?.status || data.status || (resources.length ? 'completed' : 'empty')), ...(presentationStatus ? { presentationStatus } : {}) };
}

export function requestVideoRecommendations(scope: VideoRecommendationScope, headers: Record<string, string> = {}, refresh = false): Promise<VideoRecommendationResult> {
  const key = videoRecommendationScope(scope);
  if (!key) return Promise.resolve({ resources: [], status: 'empty' });
  const requestKey = `${key}|${refresh ? 'refresh' : 'read'}`;
  let request = requests.get(requestKey);
  if (!request) {
    request = fetch('/api/resources/recommendations/for-learning', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({ ...scope, resourceTypes: ['video'], refresh }),
    }).then(async (response) => {
      if (!response.ok) throw new Error(`video recommendations failed (${response.status})`);
      return normalizeVideoRecommendations(await response.json());
    });
    requests.set(requestKey, request);
    request.catch(() => requests.delete(requestKey));
  }
  return request;
}

export function retryVideoRecommendations(scope: VideoRecommendationScope): void {
  const key = videoRecommendationScope(scope);
  requests.delete(`${key}|read`); requests.delete(`${key}|refresh`);
}
