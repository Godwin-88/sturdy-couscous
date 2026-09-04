import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

/**
 * Normalise LLM-generated text before it hits react-markdown.
 *
 * The Financial Engineer output frequently contains:
 *   - U+2217 (∗) / U+204E / stray ＊ used for bold — map them to ASCII `*`
 *   - double-spaced `** **` strong markers and over-collapsed whitespace
 *   - NBSP/zero-width/joiners that make KaTeX/GFM treat text as literal
 *   - CRLF vs LF (harmless but noisy)
 *
 * Keep dollar signs untouched EXCEPT paired `$$...$$` / `$...$` math that
 * remark-math will handle — we only collapse *whitespace/variant* chars.
 */
export function normalizeMarkdown(text: string): string {
  if (!text) return text;
  return text
    .replace(/\u2217/g, "*") // ∗ → *
    .replace(/\u2042/g, "*") // ⁂ → *
    .replace(/\uff0a/g, "*") // fullwidth ＊ → *
    .replace(/\u00a0/g, " ") // NBSP → space
    .replace(/[\u200b-\u200f\u2060\ufeff]/g, "") // zero-width/joiners → strip
    .replace(/\r\n?/g, "\n") // CRLF → LF
    .replace(/\n{3,}/g, "\n\n") // squash ragged blanks
    .replace(/\*\*\s+\*\*/g, "** **") // no space between the two markers
    .replace(/^ {2,}/gm, "    ") // tabs→spaces; keep fence intact
    .replace(/\t/g, "    ")
    .trim();
}

/**
 * Markdown renderer for the Financial Engineer chat.
 *
 * Uses react-markdown with:
 *  - remark-gfm   -> GitHub-flavoured markdown (tables, strikethrough, task lists)
 *  - remark-math + rehype-katex -> LaTeX equations ($...$ / $$...$$)
 *
 * All output is React elements (no dangerouslySetInnerHTML), safe for arbitrary
 * LLM text. Styling is matched to the dark slate theme (see index.css).
 */
function MarkdownImpl({ text }: { text: string }) {
  return (
    <div className="markdown-body text-left text-xs leading-relaxed break-words">
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
                  className="rounded bg-slate-950/80 border border-slate-600 px-1 py-0.5 text-[11px] font-mono text-emerald-300 break-all"
                >
                  {children}
                </code>
              );
            }
            return (
              <pre className="my-1.5 overflow-x-auto rounded-md bg-slate-950/90 border border-slate-600 p-2 text-[11px] leading-relaxed font-mono text-emerald-200 break-words whitespace-pre-wrap">
                {children}
              </pre>
            );
          },
          pre: ({ children }) => <>{children}</>,
          table: ({ children }) => (
            <div className="my-1.5 overflow-x-auto rounded border border-slate-700">
              <table className="w-full text-[11px] font-mono text-slate-200 break-words">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-slate-800 text-slate-300">{children}</thead>,
          th: ({ children }) => (
            <th className="px-2 py-1 text-left font-bold border-b border-slate-600 break-words">{children}</th>
          ),
          td: ({ children }) => <td className="px-2 py-1 border-b border-slate-800 align-top break-words">{children}</td>,
          h1: ({ children }) => <h1 className="text-sm font-bold text-indigo-300 mt-2 mb-1 break-words">{children}</h1>,
          h2: ({ children }) => <h2 className="text-[13px] font-bold text-indigo-300 mt-2 mb-0.5 break-words">{children}</h2>,
          h3: ({ children }) => <h3 className="text-xs font-bold text-slate-100 mt-1.5 mb-0.5 break-words">{children}</h3>,
          h4: ({ children }) => <h4 className="text-xs font-bold text-slate-200 mt-1 mb-0.5 break-words">{children}</h4>,
          ul: ({ children }) => <ul className="my-1 list-disc pl-4 space-y-0.5 break-words">{children}</ul>,
          ol: ({ children }) => <ol className="my-1 list-decimal pl-4 space-y-0.5 break-words">{children}</ol>,
          li: ({ children }) => <li className="text-xs text-slate-200 break-words">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="my-1.5 border-l-2 border-indigo-500/60 pl-2 text-slate-300 italic break-words">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-2 border-slate-700" />,
          p: ({ children }) => <p className="my-1 text-slate-200 break-words">{children}</p>,
          strong: ({ children }) => <strong className="font-bold text-slate-50 break-words">{children}</strong>,
          em: ({ children }) => <em className="italic text-slate-100 break-words">{children}</em>,
        }}
      >
        {normalizeMarkdown(text)}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MarkdownImpl);
