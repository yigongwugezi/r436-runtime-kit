import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { LinkedQuestion, QuizResult } from '../types/assessment';
import type { ContentType } from '../components/learning/SectionContentRouter';

interface QuizCache {
  questions: LinkedQuestion[];
  quizId: string;
  answers: Record<string, string>;
  results: QuizResult[];
  totalScore: number | null;
  submitted: boolean;
  suggestion: string;
  weakPoints: any[];
}

interface LectureStore {
  lectureCache: Record<string, string>;
  loadedSectionIds: string[];
  generatedSectionIds: string[];
  quizCache: Record<string, QuizCache>;
  chatReplyCache: Record<string, string>;
  contentType: ContentType;

  setLecture: (key: string, content: string) => void;
  getLecture: (key: string) => string | undefined;
  markLoaded: (sectionId: string) => void;
  markGenerated: (sectionId: string) => void;
  setQuiz: (key: string, quiz: QuizCache) => void;
  updateQuizAnswers: (key: string, answers: Record<string, string>) => void;
  getQuiz: (key: string) => QuizCache | undefined;
  setChatReply: (key: string, reply: string) => void;
  setContentType: (t: ContentType) => void;
  clearLecture: (key: string) => void;
  clearSection: (key: string) => void;
  resetForNewSection: () => void;
}

export const useLectureStore = create<LectureStore>()(
  persist(
    (set, get) => ({
      lectureCache: {},
      loadedSectionIds: [],
      generatedSectionIds: [],
      quizCache: {},
      chatReplyCache: {},
      contentType: 'lecture',

      setLecture: (key, content) =>
        set(s => ({ lectureCache: { ...s.lectureCache, [key]: content } })),

      getLecture: (key) => get().lectureCache[key],

      markLoaded: (sectionId) =>
        set(s => ({
          loadedSectionIds: s.loadedSectionIds.includes(sectionId)
            ? s.loadedSectionIds
            : [...s.loadedSectionIds, sectionId],
        })),

      markGenerated: (sectionId) =>
        set(s => ({
          generatedSectionIds: s.generatedSectionIds.includes(sectionId)
            ? s.generatedSectionIds
            : [...s.generatedSectionIds, sectionId],
        })),

      setQuiz: (key, quiz) =>
        set(s => ({ quizCache: { ...s.quizCache, [key]: quiz } })),

      updateQuizAnswers: (key, answers) =>
        set(s => {
          const existing = s.quizCache[key];
          if (!existing) return s;
          return { quizCache: { ...s.quizCache, [key]: { ...existing, answers } } };
        }),

      getQuiz: (key) => get().quizCache[key],

      setChatReply: (key, reply) =>
        set(s => ({ chatReplyCache: { ...s.chatReplyCache, [key]: reply } })),

      setContentType: (t) => set({ contentType: t }),

      clearLecture: (key) =>
        set(s => {
          const { [key]: _, ...rest } = s.lectureCache;
          return { lectureCache: rest };
        }),

      clearSection: (key) =>
        set(s => {
          const { [key]: _, ...restLectures } = s.lectureCache;
          const { [key]: __, ...restQuizzes } = s.quizCache;
          const { [key]: ___, ...restChat } = s.chatReplyCache;
          return { lectureCache: restLectures, quizCache: restQuizzes, chatReplyCache: restChat };
        }),

      resetForNewSection: () => set({ contentType: 'lecture' }),
    }),
    {
      name: 'lecture-store',
      partialize: (state) => ({
        lectureCache: state.lectureCache,
        loadedSectionIds: state.loadedSectionIds,
        generatedSectionIds: state.generatedSectionIds,
        quizCache: state.quizCache,
        chatReplyCache: state.chatReplyCache,
        contentType: state.contentType,
      }),
    }
  )
);
