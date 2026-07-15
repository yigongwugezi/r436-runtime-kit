import { create } from 'zustand';
import type { Learner, RegisterRequest } from '../types/auth';
import * as authApi from '../api/auth';
import { runtimeStorageKeys, readStorageItem, readStorageJson, writeStorageItem, writeStorageJson } from '../utils/storageKeys';
// NOTE: Do NOT statically import subjectStore/chatStore here — that creates a circular
// dependency (authStore → subjectStore → authStore).  Instead those stores subscribe
// to authStore changes and react autonomously.

/** Legacy learner from old localStorage-only system */
interface LegacyLearner {
  id: string;
  name: string;
  createdAt: number;
  lastLoginAt: number;
}

interface AuthStore {
  learner: Learner | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  loading: boolean;

  login: (identifier: string, password: string) => Promise<Learner>;
  register: (data: RegisterRequest) => Promise<Learner>;
  logout: () => void;
  fetchMe: () => Promise<Learner | null>;
  updateProfile: (updates: Partial<Pick<Learner, 'nickname' | 'grade' | 'target_exam' | 'school'>>) => Promise<void>;
  restore: () => Promise<void>;
}

function persist(token: string, refreshToken: string) {
  try {
    writeStorageItem(runtimeStorageKeys.authToken, token);
    writeStorageItem(runtimeStorageKeys.refreshToken, refreshToken);
  } catch { /* noop */ }
}

function clearStorage() {
  try {
    writeStorageItem(runtimeStorageKeys.authToken, '');
    writeStorageItem(runtimeStorageKeys.refreshToken, '');
  } catch { /* noop */ }
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  learner: null,
  token: null,
  refreshToken: null,
  isAuthenticated: false,
  loading: false,

  login: async (identifier, password) => {
    // Auto-detect: digits-only -> phone, otherwise student_no
    const isPhone = /^\d+$/.test(identifier) && identifier.length >= 11;
    const body = isPhone ? { phone: identifier, password } : { student_no: identifier, password };
    const res = await authApi.login(body);
    persist(res.access_token, res.refresh_token);
    set({
      learner: res.learner,
      token: res.access_token,
      refreshToken: res.refresh_token,
      isAuthenticated: true,
    });
    return res.learner;
  },

  register: async (data) => {
    const res = await authApi.register(data);
    persist(res.access_token, res.refresh_token);
    set({
      learner: res.learner,
      token: res.access_token,
      refreshToken: res.refresh_token,
      isAuthenticated: true,
    });
    return res.learner;
  },

  logout: () => {
    authApi.logout().catch(() => {});
    clearStorage();
    set({ learner: null, token: null, refreshToken: null, isAuthenticated: false });
  },

  fetchMe: async () => {
    try {
      const res = await authApi.getMe();
      set({ learner: res.learner, isAuthenticated: true });
      return res.learner;
    } catch {
      set({ learner: null, isAuthenticated: false });
      return null;
    }
  },

  updateProfile: async (updates) => {
    const res = await authApi.updateProfile(updates);
    set({ learner: res.learner });
  },

  restore: async () => {
    set({ loading: true });
    try {
      const token = readStorageItem(runtimeStorageKeys.authToken);
      if (token) {
        set({ token });
        const learner = await get().fetchMe();
        if (learner) {
          set({ loading: false });
          return;
        }
      }

      const refreshToken = readStorageItem(runtimeStorageKeys.refreshToken);
      if (refreshToken) {
        const refreshed = await authApi.refreshToken();
        persist(refreshed.access_token, refreshed.refresh_token);
        set({
          learner: refreshed.learner,
          token: refreshed.access_token,
          refreshToken: refreshed.refresh_token,
          isAuthenticated: true,
          loading: false,
        });
        return;
      }
    } catch { /* token invalid */ }

    // Fallback: check for legacy localStorage learner (pre-M1)
    const legacy = readStorageJson<LegacyLearner | null>(
      runtimeStorageKeys.activeLearner,
      null,
    );
    if (legacy && !get().learner) {
      // Legacy learner exists but no server account — redirect to login
      set({ loading: false });
      return;
    }

    set({ loading: false });
  },
}));

/** Get current learner synchronously (for non-React contexts like API interceptors) */
export function getCurrentLearner(): Learner | null {
  return useAuthStore.getState().learner;
}

/** Stable, opaque browser identity for the no-login compatibility path. */
export function getStableLearnerId(): string {
  const learner = getCurrentLearner();
  if (learner?.id) return learner.id;
  const stored = readStorageItem(runtimeStorageKeys.anonymousLearner);
  if (stored) return stored;
  const random = globalThis.crypto?.randomUUID?.() ?? 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, token => {
    const value = Math.floor(Math.random() * 16);
    return (token === 'x' ? value : (value & 0x3) | 0x8).toString(16);
  });
  const id = `anon_${random}`;
  writeStorageItem(runtimeStorageKeys.anonymousLearner, id);
  return id;
}

/** Get legacy learner (for migration prompts) */
export function getLegacyLearner(): LegacyLearner | null {
  try {
    return readStorageJson<LegacyLearner | null>(runtimeStorageKeys.activeLearner, null);
  } catch {
    return null;
  }
}
