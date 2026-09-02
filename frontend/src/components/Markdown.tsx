import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

/**
 * Markdown renderer for the Financial Engineer chat.
 *
 * Uses react-markdown with:
 *  - remark-gfm   -> GitHub-flavoured markdown (tables, strikethrough, task lists)
 *  - remark-math + rehype-katex -> LaTeX equations ($...$ / $$...$$) rendered via KaTeX
 *
 * All output is React elements (no dangerouslySetInnerHTML), safe for arbitrary LLM text.
 * Styling is matched to the dark slate theme (see ./index.css for .markdown-body rules).
 */
function MarkdownImpl({ text }: { text: string }) {
  return (
    <div className="markdown-body text-left text-xs leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer" className="text-indigo-400 underline" />
          ),
          code: ({ node: _node, className, children, ...props }) => {
            const isInline = !className && !String(children).includes("\n");
            if (isInline) {
              return (
                <code
                  {...props}
                  className="rounded bg-slate-950/80 border border-slate-600 px-1 py-0.5 text-[11px] font-mono text-emerald-300"
                >
                  {children}
                </code>
              );
            }
            return (
              <pre className="my-1.5 overflow-x-auto rounded-md bg-slate-950/90 border border-slate-600 p-2 text-[11px] leading-relaxed font-mono text-emerald-200">
                {children}
              </pre>
            );
          },
          pre: ({ children }) => <>{children}</>,
          table: ({ children }) => (
            <div className="my-1.5 overflow-x-auto rounded border border-slate-700">
              <table className="w-full text-[11px] font-mono text-slate-200">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-800 text-slate-300">{children}</thead>,
          th: ({ children }) => (
            <th className="px-2 py-1 text-left font-bold border-b border-slate-600">{children}</th>
          ),
          td: ({ children }) => <td className="px-2 py-1 border-b border-slate-800 align-top">{children}</td>,
          h1: ({ children }) => <h1 className="text-sm font-bold text-indigo-300 mt-2 mb-1">{children}</h1>,
          h2: ({ children }) => <h2 className="text-[13px] font-bold text-indigo-300 mt-2 mb-0.5">{children}</h2>,
          h3: ({ children }) => <h3 className="text-xs font-bold text-slate-100 mt-1.5 mb-0.5">{children}</h3>,
          h4: ({ children }) => <h4 className="text-xs font-bold text-slate-200 mt-1 mb-0.5">{children}</h4>,
          ul: ({ children }) => <ul className="my-1 list-disc pl-4 space-y-0.5">{children}</ul>,
          ol: ({ children }) => <ol className="my-1 list-decimal pl-4 space-y-0.5">{children}</ol>,
          li: ({ children }) => <li className="text-xs text-slate-200">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="my-1.5 border-l-2 border-indigo-500/60 pl-2 text-slate-300 italic">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-2 border-slate-700" />,
          p: ({ children }) => <p className="my-1 text-slate-200">{children}</p>,
          strong: ({ children }) => <strong className="font-bold text-slate-50">{children}</strong>,
          em: ({ children }) => <em className="italic text-slate-100">{children}</em>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MarkdownImpl);
