// ================================================================
// Textbook types
// ================================================================

export interface Textbook {
  id: string;
  subjectId: string;
  title: string | null;
  author: string | null;
  filename: string;
  fileSizeBytes: number;
  pageCount: number;
  status: TextbookStatus;
  parseError: string | null;
  chaptersJson: TextbookChapter[] | null;
  createdAt: number;
  updatedAt: number;
}

export type TextbookStatus = 'uploading' | 'processing' | 'ready' | 'error';

export interface TextbookChapter {
  chapterId: string;
  title: string;
  order: number;
  startPage: number;
  endPage: number;
  sections: TextbookSection[];
}

export interface TextbookSection {
  sectionId: string;
  title: string;
  order: number;
  startPage: number;
  endPage: number;
  estimatedMinutes: number;
  knowledgePoints: string[];
}

export interface TextbookTOC {
  textbook: Textbook;
  chapters: TextbookChapter[];
}

export interface TextbookContent {
  textbookId: string;
  sectionId: string | null;
  pageStart: number;
  pageEnd: number;
  content: string;
}

/** Backend response shapes (snake_case → camelCase conversion) */

export interface TextbookResponse {
  id: string;
  subject_id: string;
  title: string | null;
  author: string | null;
  filename: string;
  file_size_bytes: number;
  page_count: number;
  status: TextbookStatus;
  parse_error: string | null;
  chapters_json: TextbookChapterResponse[] | null;
  created_at: number;
  updated_at: number;
}

export interface TextbookChapterResponse {
  chapter_id: string;
  title: string;
  order: number;
  start_page: number;
  end_page: number;
  sections: TextbookSectionResponse[];
}

export interface TextbookSectionResponse {
  section_id: string;
  title: string;
  order: number;
  start_page: number;
  end_page: number;
  estimated_minutes: number;
  knowledge_points: string[];
}

export interface TextbookContentResponse {
  textbook_id: string;
  section_id: string | null;
  page_start: number;
  page_end: number;
  content: string;
}

/** Convert backend snake_case response to frontend camelCase type */
export function textbookFromResponse(raw: TextbookResponse): Textbook {
  return {
    id: raw.id,
    subjectId: raw.subject_id,
    title: raw.title,
    author: raw.author,
    filename: raw.filename,
    fileSizeBytes: raw.file_size_bytes,
    pageCount: raw.page_count,
    status: raw.status,
    parseError: raw.parse_error,
    chaptersJson: raw.chapters_json?.map(chapterFromResponse) ?? null,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function clampPage(n: number): number {
  return n > 0 ? n : 1;
}

export function chapterFromResponse(raw: TextbookChapterResponse): TextbookChapter {
  return {
    chapterId: raw.chapter_id,
    title: raw.title,
    order: raw.order,
    startPage: clampPage(raw.start_page),
    endPage: clampPage(raw.end_page),
    sections: raw.sections?.map(sectionFromResponse) ?? [],
  };
}

export function sectionFromResponse(raw: TextbookSectionResponse): TextbookSection {
  return {
    sectionId: raw.section_id,
    title: raw.title,
    order: raw.order,
    startPage: clampPage(raw.start_page),
    endPage: clampPage(raw.end_page),
    estimatedMinutes: raw.estimated_minutes,
    knowledgePoints: raw.knowledge_points ?? [],
  };
}

export function contentFromResponse(raw: TextbookContentResponse): TextbookContent {
  return {
    textbookId: raw.textbook_id,
    sectionId: raw.section_id,
    pageStart: raw.page_start,
    pageEnd: raw.page_end,
    content: raw.content,
  };
}
