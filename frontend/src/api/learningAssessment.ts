import client from './client';

export interface AssessmentResult {
  status: string;
  scores?: Record<string, number>;
  summary?: string;
  recommended_actions?: string;
  generated_at?: string;
}

export async function generateAssessment(sessionId: string): Promise<{ data?: AssessmentResult }> {
  try {
    const { data } = await client.post('/api/learning-assessment/generate', null, {
      params: { sessionId },
    });
    return data as { data?: AssessmentResult };
  } catch {
    return {};
  }
}
