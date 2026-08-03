import { Check, Copy } from "@phosphor-icons/react";
import { memo, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

function CodeBlock({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = extractText(children);
  return (
    <div className="group/code relative my-2 overflow-hidden rounded-md border bg-muted/60">
      <button
        type="button"
        aria-label="Copy code"
        className="absolute right-1.5 top-1.5 rounded border bg-card p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover/code:opacity-100"
        onClick={() => {
          void navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
      >
        {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
      </button>
      <pre className="overflow-x-auto p-3 text-xs leading-relaxed">{children}</pre>
    </div>
  );
}

function extractText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    return extractText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

/** WYSIWYG rendering for assistant replies — bold, italics, lists, tables,
 *  code — styled to the app's design tokens. Memoized: during streaming this
 *  re-renders every frame, so keep the tree cheap. */
export const ChatMarkdown = memo(function ChatMarkdown({
  content,
  className,
}: {
  content: string;
  className?: string;
}) {
  return (
    <div className={cn("chat-prose text-sm leading-relaxed", className)}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h3 className="mb-1.5 mt-3 text-base font-semibold">{children}</h3>,
          h2: ({ children }) => <h4 className="mb-1 mt-3 text-sm font-semibold">{children}</h4>,
          h3: ({ children }) => <h5 className="mb-1 mt-2 text-sm font-semibold">{children}</h5>,
          p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
          ul: ({ children }) => (
            <ul className="my-1.5 list-disc space-y-0.5 pl-5 marker:text-muted-foreground">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-1.5 list-decimal space-y-0.5 pl-5 marker:text-muted-foreground">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="[&>p]:my-0">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary underline underline-offset-2"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-primary/40 pl-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-border" />,
          code: ({ className: codeClass, children }) => {
            // block code carries a language- class or a newline; inline doesn't
            const isBlock =
              (typeof codeClass === "string" && codeClass.includes("language-")) ||
              extractText(children).includes("\n");
            if (isBlock) return <code>{children}</code>;
            return (
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
                {children}
              </code>
            );
          },
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto rounded-md border">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-muted/60">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b px-2.5 py-1.5 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border-b px-2.5 py-1.5 align-top last:border-b-0 tabular-nums">
              {children}
            </td>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
});
