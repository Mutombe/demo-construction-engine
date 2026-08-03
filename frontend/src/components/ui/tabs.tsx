import { createContext, useContext, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const TabsContext = createContext<{ value: string; setValue: (v: string) => void } | null>(null);

export function Tabs({
  defaultValue,
  value: controlled,
  onValueChange,
  children,
  className,
}: {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  children: ReactNode;
  className?: string;
}) {
  const [internal, setInternal] = useState(defaultValue ?? "");
  const value = controlled ?? internal;
  const setValue = (v: string) => {
    setInternal(v);
    onValueChange?.(v);
  };
  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex items-center gap-1 rounded-lg bg-muted p-1 text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  children,
  className,
}: {
  value: string;
  children: ReactNode;
  className?: string;
}) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("TabsTrigger must be inside Tabs");
  const active = ctx.value === value;
  return (
    <button
      role="tab"
      aria-selected={active}
      type="button"
      onClick={() => ctx.setValue(value)}
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-background text-foreground shadow-sm"
          : "hover:bg-background/60 hover:text-foreground",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string;
  children: ReactNode;
  className?: string;
}) {
  const ctx = useContext(TabsContext);
  if (!ctx || ctx.value !== value) return null;
  return (
    <div role="tabpanel" className={cn("mt-4", className)}>
      {children}
    </div>
  );
}
