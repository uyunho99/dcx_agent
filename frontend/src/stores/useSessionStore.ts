"use client";
import { create } from "zustand";
import type { Keyword, SessionData, ProjectContext } from "@/lib/types";
import { persistSid, clearPersistedSid } from "@/lib/sessionPersist";
import { patchSession } from "@/lib/api/context";
import { saveSession } from "@/lib/api";

interface SessionState {
  sid: string | null;
  projectContext: ProjectContext | null;
  persistError: string | null;
  bk: string;
  pd: string;
  ages: string[];
  ar: string[];
  gens: string[];
  kw: Keyword[];
  step: string;
  sd: SessionData | null;

  // pending keywords from keyword generation
  pendingKw: Keyword[];
  lastRound: string;

  // actions
  setSession: (data: Partial<SessionState>) => void;
  addKeywords: (kw: Keyword[]) => void;
  addManualKeyword: (keyword: Keyword) => void;
  updateKeywordCategory: (id: number | string, newCat: string) => void;
  updateKeywordScore: (id: number | string, score: number, total: number) => void;
  removeKeyword: (id: number | string) => void;
  setPendingKw: (kw: Keyword[], round: string) => void;
  clearPendingKw: () => void;
  setStep: (step: string) => void;
  reset: () => void;
}

const initial = {
  sid: null,
  projectContext: null as ProjectContext | null,
  persistError: null as string | null,
  bk: "",
  pd: "",
  ages: [] as string[],
  ar: [] as string[],
  gens: [] as string[],
  kw: [] as Keyword[],
  step: "start",
  sd: null as SessionData | null,
  pendingKw: [] as Keyword[],
  lastRound: "",
};

export const useSessionStore = create<SessionState>((set, get) => ({
  ...initial,

  setSession: (data) => {
    set((state) => {
      const context = data.projectContext !== undefined ? data.projectContext : data.sd ? data.sd.projectContext ?? null : state.projectContext;
      return { ...state, ...data, projectContext: context, ...(context ? {
        bk: context.bk, pd: context.researchQuestion.text,
        ages: context.targetScope?.households ?? [], ar: context.targetScope?.ageRanges ?? [], gens: context.targetScope?.genders ?? [],
      } : {}) };
    });
    const { sid, step } = get();
    if (sid) persistSid(sid, step);
  },

  addKeywords: (newKw) =>
    set((state) => {
      const kw = [...state.kw, ...newKw];
      const sd = state.sd ? { ...state.sd, allKw: kw } : null;
      return { kw, sd };
    }),

  addManualKeyword: (keyword) =>
    set((state) => {
      const kw = [...state.kw, keyword];
      const sd = state.sd ? { ...state.sd, allKw: kw } : null;
      return { kw, sd };
    }),

  updateKeywordCategory: (id, newCat) =>
    set((state) => {
      const kw = state.kw.map((k) =>
        k.id === id ? { ...k, cat: newCat } : k
      );
      const sd = state.sd ? { ...state.sd, allKw: kw } : null;
      return { kw, sd };
    }),

  updateKeywordScore: (id, score, total) =>
    set((state) => {
      const kw = state.kw.map((k) =>
        k.id === id ? { ...k, score, total } : k
      );
      const sd = state.sd ? { ...state.sd, allKw: kw } : null;
      return { kw, sd };
    }),

  removeKeyword: (id) =>
    set((state) => {
      const kw = state.kw.filter((k) => k.id !== id);
      const sd = state.sd ? { ...state.sd, allKw: kw } : null;
      return { kw, sd };
    }),

  setPendingKw: (kw, round) => {
    set({ pendingKw: kw, lastRound: round });
    const { sid, sd } = get();
    if (sid && sd) {
      const updated = { ...sd, _pendingKw: kw, _lastRound: round };
      if (sd.schemaVersion === 2) {
        void patchSession(sid, { drafts: { keywords: { pendingKw: kw, lastRound: round } } }).catch(() => set({ persistError: "임시 저장에 실패했습니다. 다시 시도하세요." }));
      } else { void saveSession(sid, updated); }
    }
  },

  clearPendingKw: () => {
    set({ pendingKw: [], lastRound: "" });
    const { sid, sd } = get();
    if (sid && sd?.schemaVersion === 2) void patchSession(sid, { drafts: { keywords: { pendingKw: [], lastRound: "" } } }).catch(() => set({ persistError: "임시 저장에 실패했습니다. 다시 시도하세요." }));
  },

  setStep: (step) => {
    set((state) => {
      const sd = state.sd ? { ...state.sd, step } : null;
      return { step, sd };
    });
    const { sid, sd } = get();
    if (sid) {
      persistSid(sid, step);
      if (sd?.schemaVersion === 2) void patchSession(sid, { step }).catch(() => set({ persistError: "단계 저장에 실패했습니다. 다시 시도하세요." }));
    }
  },

  reset: () => {
    set(initial);
    clearPersistedSid();
  },
}));
