import { create } from 'zustand';
import { getCurrentLearner } from './authStore';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';
import * as subjectsApi from '../api/subjects';
import type { Subject } from '../types/subject';

/* ===================================================================
 * 科目存储管理 — localStorage 辅助函数（本地缓存层）
 * =================================================================== */
const subjectsKey = () => {
  const learner = getCurrentLearner();
  return runtimeStorageKeys.subjects(learner?.id || 'anonymous');
};

const activeSubjectKey = () => {
  const learner = getCurrentLearner();
  return runtimeStorageKeys.activeSubject(learner?.id || 'anonymous');
};

const createSubjectId = () => `subject_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

function loadSubjects(): Subject[] {
  return readStorageJson(subjectsKey(), []);
}

function persistSubjects(subjects: Subject[]) {
  writeStorageJson(subjectsKey(), subjects);
}

function loadActiveSubject(): Subject | null {
  return readStorageJson(activeSubjectKey(), null);
}

function persistActiveSubject(subject: Subject | null) {
  if (subject) {
    writeStorageJson(activeSubjectKey(), subject);
  } else {
    try {
      localStorage.removeItem(activeSubjectKey().primary);
      for (const legacyKey of activeSubjectKey().legacy) {
        localStorage.removeItem(legacyKey);
      }
    } catch {}
  }
}

/* ===================================================================
 * 科目 Store — API 优先 + localStorage 缓存
 * =================================================================== */
interface SubjectStore {
  subjects: Subject[];
  activeSubject: Subject | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
  create: (name: string) => Promise<Subject>;
  remove: (id: string) => Promise<void>;
  setActive: (subject: Subject) => void;
  clearError: () => void;
}

export const useSubjectStore = create<SubjectStore>((set, get) => ({
  subjects: loadSubjects(),
  activeSubject: loadActiveSubject(),
  loading: false,
  error: null,

  load: async () => {
    const learner = getCurrentLearner();
    if (!learner) {
      set({ subjects: loadSubjects(), activeSubject: loadActiveSubject(), loading: false });
      return;
    }

    set({ loading: true, error: null });

    try {
      // Fetch server-side subjects
      const serverSubjects = await subjectsApi.getPersonalSubjects();

      // Parents never have their own subjects to migrate — the server
      // already resolved the child's subjects.  Skip migration to avoid
      // a 403 from the write-protected /api/subjects/migrate endpoint.
      if (learner.role === 'parent') {
        persistSubjects(serverSubjects);
        set({ subjects: serverSubjects, activeSubject: loadActiveSubject(), loading: false });
        return;
      }

      // Check for localStorage subjects that need migration
      const localSubjects = loadSubjects();
      if (localSubjects.length > 0) {
        try {
          // Upload local subjects to server, get merged list back
          const migrated = await subjectsApi.migratePersonalSubjects(
            localSubjects.map(s => ({ name: s.name, description: s.description })),
          );
          // Use merged server result, update local cache
          persistSubjects(migrated);
          set({ subjects: migrated, activeSubject: loadActiveSubject(), loading: false });
        } catch {
          // Migration failed — use server-only list, update cache
          persistSubjects(serverSubjects);
          set({ subjects: serverSubjects, activeSubject: loadActiveSubject(), loading: false });
        }
      } else {
        // No local subjects to migrate — use server list as cache
        persistSubjects(serverSubjects);
        set({ subjects: serverSubjects, activeSubject: loadActiveSubject(), loading: false });
      }
    } catch {
      // Server unreachable — fall back to localStorage cache
      set({
        subjects: loadSubjects(),
        activeSubject: loadActiveSubject(),
        loading: false,
        error: '无法连接服务器，使用本地缓存',
      });
    }
  },

  create: async (name: string) => {
    set({ error: null });
    try {
      const serverSubject = await subjectsApi.createPersonalSubject({ name });
      // Merge with current cache to avoid races
      const updated = [...loadSubjects(), serverSubject];
      persistSubjects(updated);
      persistActiveSubject(serverSubject);
      set({ subjects: updated, activeSubject: serverSubject });
      return serverSubject;
    } catch (err: any) {
      const message = err?.message || '创建科目失败';
      set({ error: message });
      throw err;
    }
  },

  remove: async (id: string) => {
    set({ error: null });
    try {
      await subjectsApi.deletePersonalSubject(id);
      const subjects = loadSubjects().filter(s => s.id !== id);
      persistSubjects(subjects);
      const active = get().activeSubject;
      if (active?.id === id) {
        persistActiveSubject(null);
        set({ subjects, activeSubject: null });
      } else {
        set({ subjects });
      }
    } catch (err: any) {
      const message = err?.message || '删除科目失败';
      set({ error: message });
      throw err;
    }
  },

  setActive: (subject: Subject) => {
    persistActiveSubject(subject);
    set({ activeSubject: subject });
  },

  clearError: () => set({ error: null }),
}));

// React to auth changes — reload subjects on login
import { useAuthStore } from './authStore';
useAuthStore.subscribe((state, prev) => {
  if (state.isAuthenticated && !prev.isAuthenticated) {
    useSubjectStore.getState().load();
  }
});
