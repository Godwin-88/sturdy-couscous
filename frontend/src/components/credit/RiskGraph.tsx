import { useState } from "react";
import { api } from "../../lib/creditApi";
import type { GraphQueryResponse } from "../../types/credit";
import NetworkGraph from "./NetworkGraph";

const EXAMPLES = [
  "What is the relationship between Credit Risk and Collateral?",
  "Show systemic stress measures.",
  "Explain the VaR model.",
];

export default function RiskGraph() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<GraphQueryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.queryGraph(query));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Query failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <h2>Risk Graph — GraphRAG</h2>
        <label>
          Ask the financial knowledge graph
          <textarea
            rows={3}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. What drives credit default risk?"
          />
        </label>
        <button className="primary" onClick={run} disabled={busy || !query.trim()}>
          {busy ? "Reasoning…" : "Query Graph"}
        </button>
        <div className="chips">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" onClick={() => setQuery(ex)}>
              {ex}
            </button>
          ))}
        </div>
      </section>

      {error && <p className="error">{error}</p>}

      {result && (
        <section className="card animate-fade-in">
          <h3>Explanation</h3>
          <p className="explanation">{result.explanation}</p>

          <h3>Intent: {result.intent}</h3>
          {(result.entities.length > 0 || result.relationships.length > 0 || result.paths.length > 0) && (
            <>
              <h3>Knowledge Graph</h3>
              <NetworkGraph
                entities={result.entities.map((en) => ({ name: String(en.name), type: en.type }))}
                relationships={result.relationships}
                paths={result.paths.flat()}
              />
            </>
          )}

          {result.entities.length > 0 && (
            <>
              <h3>Entities</h3>
              <ul>
                {result.entities.map((en) => (
                  <li key={String(en.name)}>{String(en.name)}</li>
                ))}
              </ul>
            </>
          )}

          {result.quantitative.length > 0 && (
            <>
              <h3>Quantitative Outputs</h3>
              <div className="metric-grid">
                {result.quantitative.map((q) => (
                  <div className="metric" key={q.label}>
                    <span className="metric-label">{q.label}</span>
                    <span className="metric-value">{String(q.value)}{q.unit}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {result.relationships.length > 0 && (
            <>
              <h3>Relationships</h3>
              <ul>
                {result.relationships.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </>
          )}

          {result.paths.length > 0 && (
            <>
              <h3>Reasoning Paths</h3>
              {result.paths.map((p, i) => (
                <p key={i} className="mono">{p.join(" → ")}</p>
              ))}
            </>
          )}

          {result.traversal_error && (
            <p className="error">Traversal: {result.traversal_error}</p>
          )}
        </section>
      )}
    </div>
  );
}