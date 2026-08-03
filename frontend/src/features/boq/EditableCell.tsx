import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface EditableCellProps {
  value: string;
  onCommit: (value: string) => void;
  align?: "left" | "right";
  type?: "text" | "number";
  disabled?: boolean;
  display?: string;
  className?: string;
}

/** Click (or focus+Enter) to edit; commits on blur/Enter, reverts on Escape. */
export function EditableCell({
  value,
  onCommit,
  align = "left",
  type = "text",
  disabled,
  display,
  className,
}: EditableCellProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      setDraft(value);
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing, value]);

  const commit = () => {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  };

  if (!editing) {
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => setEditing(true)}
        onFocus={(e) => {
          // keyboard navigation: focusing the cell and pressing Enter opens the editor
          e.currentTarget.onkeydown = (ke) => {
            if (ke.key === "Enter") setEditing(true);
          };
        }}
        className={cn(
          "block h-full w-full truncate rounded-sm px-2 py-1.5 text-sm",
          align === "right" && "text-right tabular-nums",
          !disabled && "cursor-text hover:bg-accent focus-visible:bg-accent focus-visible:outline-none",
          disabled && "cursor-default",
          className,
        )}
        title={display ?? value}
      >
        {display ?? value ?? ""}
      </button>
    );
  }

  return (
    <input
      ref={inputRef}
      type={type}
      step={type === "number" ? "any" : undefined}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setEditing(false);
        if (e.key === "Tab") commit();
      }}
      className={cn(
        "h-full w-full rounded-sm border border-ring bg-card px-2 py-1.5 text-sm focus:outline-none",
        align === "right" && "text-right tabular-nums",
      )}
    />
  );
}
