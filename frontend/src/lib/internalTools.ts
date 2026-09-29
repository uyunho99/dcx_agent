"use client";
import { createContext, type Dispatch, type SetStateAction } from "react";
export const INTERNAL_TOOLS = process.env.NEXT_PUBLIC_INTERNAL_TOOLS !== "false";
export type InternalToolsState = { drawerOpen: boolean; setDrawerOpen: Dispatch<SetStateAction<boolean>> };
export const InternalToolsContext = createContext<InternalToolsState | null>(null);
