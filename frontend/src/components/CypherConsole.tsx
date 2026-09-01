import { useState } from "react";
import { Play, RotateCcw, AlertCircle, CheckCircle2 } from "lucide-react";
import { researchApi } from "@/lib/api";
import clsx from "clsx";

export default function CypherConsole() {
  const [query, setQuery] = useState("MATCH (n) RETURN n LIMIT 25");
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [execTime, setExecTime] = useState<number | null>(null);

  const runQuery = async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    const start = performance.now();
    try {
      const res = await researchApi.graphQuery(query);
      setResults(res.results);
      setExecTime(res.execution_time_ms || Math.round(performance.now() - start));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const columns = results && results.length > 0
    ? Object.keys(results[0])
    : [];

  return (
    <div className="h-full flex flex-col gap-3 p-3">
      {/* Query editor */}
      <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Cypher Query</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setQuery("MATCH (n) RETURN n LIMIT 25"); setResults(null); setError(null); }}
              className="p-1 text-slate-500 hover:text-slate-300 rounded"
              title="Reset"
            >
              <RotateCcw size={14} />
            </button>
            <button
              onClick={runQuery}
              disabled={loading || !query.trim()}
              className={clsx(
                "flex items-center gap-1 px-3 py-1 rounded text-xs font-semibold transition-colors",
                loading
                  ? "bg-indigo-800/50 text-indigo-300 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500 text-white"
              )}
            >
              <Play size={12} />
              {loading ? "Running..." : "Run"}
            </button>
          </div>
        </div>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="w-full bg-slate-950 text-slate-200 font-mono text-xs p-3 resize-none outline-none border-0"
          rows={6}
          placeholder="Write your Cypher query here..."
          spellCheck={false}
        />
      </div>

      {/* Results area */}
      <div className="flex-1 rounded-xl border border-slate-700 bg-slate-900 overflow-hidden flex flex-col min-h-0">
        <div className="flex items-center justify-between px-3 py-2 bg-slate-800 border-b border-slate-700 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Results</span>
            {results && (
              <span className="text-[10px] text-slate-500">
                {results.length} rows{execTime ? ` · ${execTime}ms` : ""}
              </span>
            )}
          </div>
          {error && (
            <div className="flex items-center gap-1 text-[10px] text-red-400">
              <AlertCircle size={12} />
              Error
            </div>
          )}
          {results && !error && (
            <div className="flex items-center gap-1 text-[10px] text-emerald-400">
              <CheckCircle2 size={12} />
              Success
            </div>
          )}
        </div>

        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-full text-xs text-slate-500 animate-pulse">
              Executing query...
            </div>
          )}
          {error && (
            <div className="p-4 text-xs text-red-400 font-mono whitespace-pre-wrap">
              {error}
            </div>
          )}
          {results && results.length === 0 && !loading && (
            <div className="flex items-center justify-center h-full text-xs text-slate-500">
              No results returned
            </div>
          )}
          {results && results.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="bg-slate-800/50">
                    <th className="text-left px-3 py-2 text-slate-400 font-semibold sticky top-0 bg-slate-800/50">#</th>
                    {columns.map(col => (
                      <th key={col} className="text-left px-3 py-2 text-slate-400 font-semibold sticky top-0 bg-slate-800/50 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.map((row, i) => (
                    <tr key={i} className={clsx("border-t border-slate-800", i % 2 === 0 ? "bg-slate-900" : "bg-slate-900/50")}>
                      <td className="px-3 py-1.5 text-slate-600">{i + 1}</td>
                      {columns.map(col => (
                        <td key={col} className="px-3 py-1.5 text-slate-300 max-w-[300px] truncate">
                          {formatCellValue(row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatCellValue(v: unknown): string {
  if (v === null || v === undefined) return <span className="text-slate-600 italic">null</span> as unknown as string;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}