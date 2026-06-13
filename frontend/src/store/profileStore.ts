import { create } from 'zustand';
import type { StudentProfile, KnowledgeGap } from '../types/profile';

interface ProfileStore {
  profile: StudentProfile | null;
  loading: boolean;
  error: string | null;

  setProfile: (p: StudentProfile) => void;
  updateDimension: (key: string, value: number) => void;
  setWeaknesses: (gaps: KnowledgeGap[]) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  clearProfile: () => void;
}

export const useProfileStore = create<ProfileStore>((set) => ({
  profile: null,
  loading: false,
  error: null,

  setProfile: (p) => set({ profile: p, error: null }),
  updateDimension: (key, value) =>
    set((s) => {
      if (!s.profile) return s;
      return {
        profile: {
          ...s.profile,
          dimensions: s.profile.dimensions.map((d) =>
            d.key === key ? { ...d, value, updatedAt: Date.now() } : d,
          ),
        },
      };
    }),
  setWeaknesses: (gaps) =>
    set((s) => {
      if (!s.profile) return s;
      return { profile: { ...s.profile, weaknesses: gaps } };
    }),
  setLoading: (v) => set({ loading: v }),
  setError: (e) => set({ error: e }),
  clearProfile: () => set({ profile: null, error: null }),
}));
