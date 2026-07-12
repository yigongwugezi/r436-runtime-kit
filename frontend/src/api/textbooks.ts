/** Textbook API client — upload, query, and manage textbooks. */

import client from './client';
import {
  textbookFromResponse,
  chapterFromResponse,
  contentFromResponse,
  type Textbook,
  type TextbookContent,
  type TextbookTOC,
} from '../types/textbook';

/** Upload a PDF textbook for a personal subject. */
export async function uploadTextbook(
  subjectId: string,
  file: File,
): Promise<Textbook> {
  const formData = new FormData();
  formData.append('subject_id', subjectId);
  formData.append('file', file);
  const res = await client.post('/api/textbooks/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000, // 2 min timeout for upload + initial processing
  });
  return textbookFromResponse(res.data.textbook);
}

/** Get textbook metadata for a subject. */
export async function getTextbook(subjectId: string): Promise<Textbook | null> {
  const res = await client.get(`/api/textbooks/${subjectId}`);
  const tb = res.data?.textbook;
  return tb ? textbookFromResponse(tb) : null;
}

/** Get textbook TOC (chapters + sections). */
export async function getTextbookTOC(subjectId: string): Promise<TextbookTOC | null> {
  const res = await client.get(`/api/textbooks/${subjectId}/toc`);
  const toc = res.data?.toc;
  if (!toc) return null;
  return {
    textbook: textbookFromResponse(toc.textbook),
    chapters: (toc.chapters ?? []).map(chapterFromResponse),
  };
}

/** Get extracted markdown content for a textbook section or page range. */
export async function getTextbookContent(
  subjectId: string,
  options: { sectionId?: string; pageStart?: number; pageEnd?: number } = {},
): Promise<TextbookContent | null> {
  const params: Record<string, string> = {};
  if (options.sectionId) params.section_id = options.sectionId;
  if (options.pageStart) params.page_start = String(options.pageStart);
  if (options.pageEnd) params.page_end = String(options.pageEnd);
  const res = await client.get(`/api/textbooks/${subjectId}/content`, { params });
  const content = res.data?.content;
  return content ? contentFromResponse(content) : null;
}

/** Trigger LLM re-parsing of a textbook. */
export async function parseTextbook(subjectId: string): Promise<Textbook> {
  const res = await client.post(`/api/textbooks/${subjectId}/parse`);
  return textbookFromResponse(res.data.textbook);
}

/** Get the URL for a rendered PDF page image. */
export function getTextbookPageUrl(subjectId: string, pageNum: number, zoom = 1.5): string {
  return `/api/textbooks/${encodeURIComponent(subjectId)}/pages/${pageNum}?zoom=${zoom}`;
}

/** Get the URL for the raw PDF file. */
export function getTextbookPdfUrl(subjectId: string): string {
  return `/api/textbooks/${encodeURIComponent(subjectId)}/pdf`;
}

/** Delete a textbook from a subject. */
export async function deleteTextbook(subjectId: string): Promise<void> {
  await client.delete(`/api/textbooks/${subjectId}`);
}

/** List all textbooks for the current learner (resource library). */
export async function listTextbooks(): Promise<Textbook[]> {
  const res = await client.get('/api/textbooks');
  const textbooks = res.data?.textbooks ?? [];
  return textbooks.map(textbookFromResponse);
}
