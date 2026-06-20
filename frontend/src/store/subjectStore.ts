import { create } from 'zustand';
import { getCurrentLearner } from '../pages/LoginPage';
import { readStorageJson, writeStorageJson, runtimeStorageKeys } from '../utils/storageKeys';

/* ===================================================================
 * 科目（Subject）类型定义
 * =================================================================== */
export interface Subject {
  id: string;
  name: string;
  description?: string;
  createdAt: number;
  updatedAt: number;
}

/* ===================================================================
 * 科目存储管理
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
 * 科目 Store
 * =================================================================== */
interface SubjectStore {
  subjects: Subject[];
  activeSubject: Subject | null;
  load: () => void;
  create: (name: string) => Subject;
  remove: (id: string) => void;
  setActive: (subject: Subject) => void;
}

export const useSubjectStore = create<SubjectStore>((set, get) => ({
  subjects: loadSubjects(),
  activeSubject: loadActiveSubject(),

  load: () => {
    set({ subjects: loadSubjects(), activeSubject: loadActiveSubject() });
  },

  create: (name: string) => {
    const subject: Subject = {
      id: createSubjectId(),
      name,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    const subjects = [...loadSubjects(), subject];
    persistSubjects(subjects);
    persistActiveSubject(subject);
    set({ subjects, activeSubject: subject });
    return subject;
  },

  remove: (id: string) => {
    const subjects = loadSubjects().filter(s => s.id !== id);
    persistSubjects(subjects);
    const active = get().activeSubject;
    if (active?.id === id) {
      persistActiveSubject(null);
      set({ subjects, activeSubject: null });
    } else {
      set({ subjects });
    }
  },

  setActive: (subject: Subject) => {
    persistActiveSubject(subject);
    set({ activeSubject: subject });
  },
}));
