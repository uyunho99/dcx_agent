"use client";
import { createContext, useCallback, useContext, useRef, type ReactNode } from 'react';
import { allowNavigation } from '@/lib/logic/finalFix';
const Context = createContext<{register: (id: string, dirty: boolean) => void; confirmNavigation: () => boolean}>({register: () => {}, confirmNavigation: () => true});
export const useDirty = () => useContext(Context);
export function DirtyProvider({children}: {children: ReactNode}) {
 const entries = useRef(new Set<string>());
 const register = useCallback((id: string, dirty: boolean) => { if(dirty) entries.current.add(id); else entries.current.delete(id); }, []);
 const confirmNavigation = useCallback(() => allowNavigation(entries.current.size > 0, message => window.confirm(message)), []);
 return <Context.Provider value={{register, confirmNavigation}}>{children}</Context.Provider>;
}
