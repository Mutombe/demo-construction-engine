import { RichMarkdown } from "@/components/ui/markdown";

/** Chat-scale wrapper around the app's shared editorial renderer. */
export function ChatMarkdown({ content, className }: { content: string; className?: string }) {
  return <RichMarkdown content={content} variant="chat" className={className} />;
}
