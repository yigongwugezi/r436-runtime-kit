import client from './client';

export interface AssessmentResult {
  status: string;
  scores?: Record<string, number>;
  summary?: string;
  recommended_actions?: string;
  generated_at?: string;
  cached?: boolean;
  generatedAt?: string;
  errorCode?: 'provider_unavailable' | 'insufficient_data' | 'invalid_output' | 'generation_failed' | 'unauthorized' | 'forbidden';
}

export async function generateAssessment(params: { sessionId: string; subjectId?: string }): Promise<{ data?: AssessmentResult }> {
  const { data } = await client.post('/api/learning-assessment/generate', null, { params });
  return data as { data?: AssessmentResult };
}
