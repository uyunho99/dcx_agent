"use client";
import { create } from "zustand";
import type { Keyword, SessionData } from "@/lib/types";

interface SessionState {
  sid: string | null;
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
  setPendingKw: (kw: Keyword[], round: string) => void;
  clearPendingKw: () => void;
  setStep: (step: string) => void;
  reset: () => void;
}

const initial = {
  sid: null,
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

export const useSessionStore = create<SessionState>((set) => ({
  ...initial,

  setSession: (data) =>
    set((state) => ({ ...state, ...data })),

  addKeywords: (newKw) =>
    set((state) => {
      const kw = [...state.kw, ...newKw];
      const sd = state.sd ? { ...state.sd, allKw: kw } : null;
      return { kw, sd };
    }),

  setPendingKw: (kw, round) =>
    set({ pendingKw: kw, lastRound: round }),

  clearPendingKw: () =>
    set({ pendingKw: [], lastRound: "" }),

  setStep: (step) =>
    set((state) => {
      const sd = state.sd ? { ...state.sd, step } : null;
      return { step, sd };
    }),

  reset: () => set(initial),
}));
