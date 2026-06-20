type StorageKeyPair = {
  primary: string;
  legacy: string[];
};

const readItem = (pair: StorageKeyPair): string | null => {
  try {
    const current = localStorage.getItem(pair.primary);
    if (current !== null) return current;
    for (const key of pair.legacy) {
      const legacy = localStorage.getItem(key);
      if (legacy !== null) {
        localStorage.setItem(pair.primary, legacy);
        return legacy;
      }
    }
  } catch {
    // noop
  }
  return null;
};

const writeItem = (pair: StorageKeyPair, value: string) => {
  try {
    localStorage.setItem(pair.primary, value);
    for (const key of pair.legacy) {
      localStorage.removeItem(key);
    }
  } catch {
    // noop
  }
};

const readJson = <T>(pair: StorageKeyPair, fallback: T): T => {
  const raw = readItem(pair);
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
};

const writeJson = (pair: StorageKeyPair, value: unknown) => {
  writeItem(pair, JSON.stringify(value));
};

export const runtimeStorageKeys = {
  learners: {
    primary: 'r436_runtime_learners',
    legacy: ['eduagent_learners'],
  },
  activeLearner: {
    primary: 'r436_runtime_active_learner',
    legacy: ['eduagent_active_learner'],
  },
  learningPrefs: {
    primary: 'r436_runtime_learning_preferences',
    legacy: ['eduagent_learning_preferences'],
  },
  learnerName: {
    primary: 'r436_runtime_learner_name',
    legacy: ['eduagent_learner_name'],
  },
  chatSession: (suffix: string) => ({
    primary: `r436_runtime_session_${suffix}`,
    legacy: [`eduagent_session_${suffix}`],
  }),
  chatSessions: (suffix: string) => ({
    primary: `r436_runtime_sessions_${suffix}`,
    legacy: [`eduagent_sessions_${suffix}`],
  }),
  subjects: (learnerId: string) => ({
    primary: `r436_runtime_subjects_${learnerId}`,
    legacy: [`eduagent_subjects_${learnerId}`],
  }),
  activeSubject: (learnerId: string) => ({
    primary: `r436_runtime_active_subject_${learnerId}`,
    legacy: [`eduagent_active_subject_${learnerId}`],
  }),
} satisfies Record<string, StorageKeyPair | ((suffix: string) => StorageKeyPair)>;

export { readItem as readStorageItem, writeItem as writeStorageItem, readJson as readStorageJson, writeJson as writeStorageJson };
