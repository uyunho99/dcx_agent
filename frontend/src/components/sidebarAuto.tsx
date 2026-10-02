'use client';
import { createContext, useContext, useMemo, type ReactNode } from 'react';

export function createSidebarAuto(onChange: (active: boolean) => void) {
  let count = 0;
  return {
    request() {
      count += 1;
      if (count === 1) onChange(true);
      let released = false;
      return () => {
        if (released) return;
        released = true;
        count -= 1;
        if (count === 0) onChange(false);
      };
    },
  };
}

export function sidebarCollapsed(user: boolean, auto: boolean) {
  return user || auto;
}

const SidebarAutoContext = createContext<ReturnType<typeof createSidebarAuto>>({
  request: () => () => {},
});

export function SidebarAutoProvider({ children, onChange }: {
  children: ReactNode;
  onChange: (active: boolean) => void;
}) {
  const auto = useMemo(() => createSidebarAuto(onChange), [onChange]);
  return <SidebarAutoContext.Provider value={auto}>{children}</SidebarAutoContext.Provider>;
}

export function useSidebarAuto() {
  return useContext(SidebarAutoContext);
}
