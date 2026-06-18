import { create } from 'zustand';
import type { StudentProfile, KnowledgeGap } from '../types/profile';

/* ===================================================================
 * 科目级画像存储
 * 每个科目拥有独立的画像数据，切换科目时自动隔离
 * =================================================================== */
interface ProfileStore {
  /** keyed by subjectId */
  profiles: Record<string, StudentProfile | null>;
  loadingMap: Record<string, boolean>;
  errorMap: Record<string, string | null>;

  setProfile: (subjectId: string, p: StudentProfile) => void;
  updateDimension: (subjectId: string, key: string, value: number) => void;
  setWeaknesses: (subjectId: string, gaps: KnowledgeGap[]) => void;
  setLoading: (subjectId: string, v: boolean) => void;
  setError: (subjectId: string, e: string | null) => void;
  clearSubject: (subjectId: string) => void;
  clearAll: () => void;
}

export const useProfileStore = create<ProfileStore>((set) => ({
  profiles: {},
  loadingMap: {},
  errorMap: {},

  setProfile: (subjectId, p) =>
    set((s) => ({
      profiles: { ...s.profiles, [subjectId]: p },
      errorMap: { ...s.errorMap, [subjectId]: null },
    })),

  updateDimension: (subjectId, key, value) =>
    set((s) => {
      const profile = s.profiles[subjectId];
      if (!profile) return s;
      return {
        profiles: {
          ...s.profiles,
          [subjectId]: {
            ...profile,
            dimensions: profile.dimensions.map((d) =>
              d.key === key ? { ...d, value, updatedAt: Date.now() } : d,
            ),
          },
        },
      };
    }),

  setWeaknesses: (subjectId, gaps) =>
    set((s) => {
      const profile = s.profiles[subjectId];
      if (!profile) return s;
      return {
        profiles: {
          ...s.profiles,
          [subjectId]: { ...profile, weaknesses: gaps },
        },
      };
    }),

  setLoading: (subjectId, v) =>
    set((s) => ({ loadingMap: { ...s.loadingMap, [subjectId]: v } })),

  setError: (subjectId, e) =>
    set((s) => ({ errorMap: { ...s.errorMap, [subjectId]: e } })),

  clearSubject: (subjectId) =>
    set((s) => {
      const { [subjectId]: _, ...rest } = s.profiles;
      const { [subjectId]: __, ...restLoading } = s.loadingMap;
      const { [subjectId]: ___, ...restError } = s.errorMap;
      return { profiles: rest, loadingMap: restLoading, errorMap: restError };
    }),

  clearAll: () => set({ profiles: {}, loadingMap: {}, errorMap: {} }),
}));
