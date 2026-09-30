"use client";
import { createContext, useContext, type Dispatch, type ReactNode, type SetStateAction } from "react";

export type InternalToolsState = { drawerOpen: boolean; setDrawerOpen: Dispatch<SetStateAction<boolean>> };
export const InternalToolsContext = createContext<InternalToolsState | null>(null);

export function InternalToolsProvider({ value, children }: { value: InternalToolsState; children: ReactNode }) {
  return <InternalToolsContext.Provider value={value}>{children}</InternalToolsContext.Provider>;
}

export function useInternalTools() {
  const context = useContext(InternalToolsContext);
  if (context === null) throw new Error("useInternalTools must be used within InternalToolsProvider");
  return context;
}
