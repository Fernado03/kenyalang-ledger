import { create } from 'zustand';

const ACCOUNTANT_ID_KEY = 'kenyalang.accountant_id';

function readStoredAccountantId(): string | null {
  try {
    return window.localStorage.getItem(ACCOUNTANT_ID_KEY);
  } catch {
    return null;
  }
}

interface SessionState {
  accountantId: string | null;
  setAccountantId: (id: string) => void;
  clearAccountantId: () => void;
}

/** Session gate state: the accountant UUID behind `X-Accountant-Id`. */
export const useSessionStore = create<SessionState>((set) => ({
  accountantId: readStoredAccountantId(),

  setAccountantId: (id: string) => {
    try {
      window.localStorage.setItem(ACCOUNTANT_ID_KEY, id);
    } catch {
      // Private-mode storage failures must not block sign-in.
    }
    set({ accountantId: id });
  },

  clearAccountantId: () => {
    try {
      window.localStorage.removeItem(ACCOUNTANT_ID_KEY);
    } catch {
      // Nothing to clean up.
    }
    set({ accountantId: null });
  },
}));
