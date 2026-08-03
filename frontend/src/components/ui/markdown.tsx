/** RichMarkdown — the app's editorial renderer for AI-generated text.
 *
 * Every surface where generation lands (chat replies, RFQ documents, PO
 * terms, weekly reports, quote analysis) renders through this component so
 * headings, lists, tables, emphasis and even bare newlines read as typeset
 * copy, never as raw markdown.
 *
 * Variants:
 *  - "chat":     compact scale for the assistant panel
 *  - "document": editorial scale for generated documents — larger headings
 *                with hairline rules, generous rhythm, lead paragraph
 *
 * remark-breaks turns single newlines into line breaks, so loosely formatted
 * AI output (terms, notes) keeps its intended line structure.
 */

import { Check, Copy } from "@phosphor-icons/react";
import { memo, useState, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

type Variant = "chat" | "document";

function extractText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (typeof node === "object" && "props" in node) {
    return extractText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

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

const SCALE: Record<
  Variant,
  { root: string; h1: string; h2: string; h3: string; p: string; li: string; table: string }
> = {
  chat: {
    root: "text-sm leading-relaxed",
    h1: "mb-1.5 mt-3 text-base font-semibold first:mt-0",
    h2: "mb-1 mt-3 text-sm font-semibold first:mt-0",
    h3: "mb-1 mt-2 text-sm font-semibold first:mt-0",
    p: "my-1.5 first:mt-0 last:mb-0",
    li: "[&>p]:my-0",
    table: "text-xs",
  },
  document: {
    root: "text-sm leading-7",
    h1: "mb-3 mt-6 border-b pb-2 text-lg font-semibold tracking-tight first:mt-0",
    h2: "mb-2 mt-5 border-b pb-1.5 text-base font-semibold tracking-tight first:mt-0",
    h3: "mb-1.5 mt-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground first:mt-0",
    p: "my-2.5 first:mt-0 last:mb-0",
    li: "[&>p]:my-0.5",
    table: "text-sm",
  },
};

export const RichMarkdown = memo(function RichMarkdown({
  content,
  variant = "chat",
  className,
}: {
  content: string;
  variant?: Variant;
  className?: string;
}) {
  const s = SCALE[variant];
  return (
    <div className={cn(s.root, className)}>
      <Markdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={{
          h1: ({ children }) => <h3 className={s.h1}>{children}</h3>,
          h2: ({ children }) => <h4 className={s.h2}>{children}</h4>,
          h3: ({ children }) => <h5 className={s.h3}>{children}</h5>,
          h4: ({ children }) => <h6 className={s.h3}>{children}</h6>,
          p: ({ children }) => <p className={s.p}>{children}</p>,
          ul: ({ children }) => (
            <ul className="my-2 list-disc space-y-1 pl-5 marker:text-muted-foreground">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-muted-foreground">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className={s.li}>{children}</li>,
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
            <blockquote className="my-2.5 border-l-2 border-primary/40 pl-3 italic text-muted-foreground">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-4 border-border" />,
          code: ({ className: codeClass, children }) => {
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
            <div className="my-2.5 overflow-x-auto rounded-md border">
              <table className={cn("w-full border-collapse", s.table)}>{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-muted/60">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b px-2.5 py-1.5 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border-b px-2.5 py-1.5 align-top tabular-nums">{children}</td>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  );
});
