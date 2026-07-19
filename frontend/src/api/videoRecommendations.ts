export type VideoRecommendationScope = {
  sessionId?: string;
  subjectId?: string;
  pathId?: string;
  stageId?: string;
  dayId?: string;
  globalDayIndex?: number;
  taskId?: string;
};

type VideoRecommendationResult = { resources: any[]; status: string };

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
  return { resources, status: String(recommendations?.status || data.status || (resources.length ? 'completed' : 'empty')) };
}

export function requestVideoRecommendations(scope: VideoRecommendationScope, headers: Record<string, string> = {}): Promise<VideoRecommendationResult> {
  const key = videoRecommendationScope(scope);
  if (!key) return Promise.resolve({ resources: [], status: 'empty' });
  let request = requests.get(key);
  if (!request) {
    request = fetch('/api/resources/recommendations/for-learning', {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({ ...scope, resourceTypes: ['video'] }),
    }).then(async (response) => {
      if (!response.ok) throw new Error(`video recommendations failed (${response.status})`);
      return normalizeVideoRecommendations(await response.json());
    });
    requests.set(key, request);
    request.catch(() => requests.delete(key));
  }
  return request;
}

export function retryVideoRecommendations(scope: VideoRecommendationScope): void {
  requests.delete(videoRecommendationScope(scope));
}
