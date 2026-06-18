import { create } from 'zustand';
import { getCurrentLearner } from '../pages/LoginPage';

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
  return `eduagent_subjects_${learner?.id || 'anonymous'}`;
};

const activeSubjectKey = () => {
  const learner = getCurrentLearner();
  return `eduagent_active_subject_${learner?.id || 'anonymous'}`;
};

const createSubjectId = () => `subject_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

function loadSubjects(): Subject[] {
  try {
    const data = localStorage.getItem(subjectsKey());
    return data ? JSON.parse(data) : [];
  } catch { return []; }
}

function persistSubjects(subjects: Subject[]) {
  try { localStorage.setItem(subjectsKey(), JSON.stringify(subjects)); } catch {}
}

function loadActiveSubject(): Subject | null {
  try {
    const data = localStorage.getItem(activeSubjectKey());
    return data ? JSON.parse(data) : null;
  } catch { return null; }
}

function persistActiveSubject(subject: Subject | null) {
  if (subject) {
    try { localStorage.setItem(activeSubjectKey(), JSON.stringify(subject)); } catch {}
  } else {
    try { localStorage.removeItem(activeSubjectKey()); } catch {}
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
