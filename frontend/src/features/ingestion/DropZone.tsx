import { UploadSimple } from "@phosphor-icons/react";
import { ClaudeIcon } from "@/components/ui/claude-icon";
import { useRef, useState } from "react";
import { useAiStatus } from "@/features/ai/useAiStatus";
import { cn } from "@/lib/utils";

export function DropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const { aiAvailable, loaded } = useAiStatus();
  const disabled = loaded && !aiAvailable;

  const handleFiles = (list: FileList | null) => {
    if (!list || disabled) return;
    onFiles(Array.from(list));
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <button
      type="button"
      disabled={disabled}
      className={cn(
        "flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors",
        dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
        disabled && "cursor-not-allowed opacity-60",
      )}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      {disabled ? (
        <>
          <ClaudeIcon className="h-8 w-8 text-muted-foreground" />
          <div className="text-sm font-medium">AI features are not configured</div>
          <div className="text-xs text-muted-foreground">
            Set ANTHROPIC_API_KEY on the backend to enable the AI inbox.
          </div>
        </>
      ) : (
        <>
          <UploadSimple className="h-8 w-8 text-primary" />
          <div className="text-sm font-medium">
            Drop invoices, receipts, delivery notes or quotes here
          </div>
          <div className="text-xs text-muted-foreground">
            JPEG, PNG, WebP or PDF up to 15 MB — Claude classifies and extracts each one; nothing
            posts without your approval.
          </div>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp,application/pdf"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </button>
  );
}
