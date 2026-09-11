import type { RiskRegime } from "../../types/credit";

interface ScenarioBuilderProps {
  source: string;
  setSource: (s: string) => void;
  borrowerId: string;
  setBorrowerId: (s: string) => void;
  regime: RiskRegime;
  setRegime: (r: RiskRegime) => void;
  exposure: number;
  setExposure: (n: number) => void;
  confidence: number;
  setConfidence: (n: number) => void;
  days: number;
  setDays: (n: number) => void;
  customPnl: string;
  setCustomPnl: (s: string) => void;
  generating: boolean;
  analyzing: boolean;
  error: string | null;
  result: {
    var: number;
    cvar: number;
    stressLoss: number;
    stressedExposure: number;
    expectedLoss: number;
  } | null;
  borrowers: string[];
  generate: () => void;
  analyze: () => void;
  applyPreset: (key: string) => void;
  SOURCES: { id: string; label: string; desc: string }[];
  REGIMES: RiskRegime[];
  SAMPLE_PRESETS: Record<string, { label: string; description: string; pnl: number[] }>;
}

export default function ScenarioBuilder({
  source, setSource,
  borrowerId, setBorrowerId,
  regime, setRegime,
  exposure, setExposure,
  confidence, setConfidence,
  days, setDays,
  customPnl, setCustomPnl,
  generating, analyzing, error, result,
  borrowers,
  generate, analyze, applyPreset,
  SOURCES, REGIMES, SAMPLE_PRESETS,
}: ScenarioBuilderProps) {
  return (
    <div className="stack">
      <section className="card animate-fade-in">
        <h2>Scenario Builder</h2>
        <p className="muted">
          Build a P&L scenario from real data, then run the full quant suite.
        </p>

        <label>
          Data Source
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((s) => (
              <option key={s.id} value={s.id}>{s.label} — {s.desc}</option>
            ))}
          </select>
        </label>

        {source === "borrower" && (
          <label>
            Borrower
            <select value={borrowerId} onChange={(e) => setBorrowerId(e.target.value)}>
              <option value="">-- select borrower --</option>
              {borrowers.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </label>
        )}

        {source === "sample" && (
          <div className="chips">
            {Object.entries(SAMPLE_PRESETS).map(([key, preset]) => (
              <button key={key} className="chip" onClick={() => applyPreset(key)} title={preset.description}>
                {preset.label}
              </button>
            ))}
          </div>
        )}

        <label>
          Market Regime
          <select value={regime} onChange={(e) => setRegime(e.target.value as RiskRegime)}>
            {REGIMES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>

        <label>
          Base Exposure (USD)
          <input
            type="number"
            min={1}
            step="any"
            value={exposure}
            onChange={(e) => setExposure(Number(e.target.value))}
          />
        </label>

        <label>
          Confidence Level
          <input
            type="number"
            min={0.5}
            max={0.99}
            step="0.01"
            value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))}
          />
        </label>

        {source === "sample" && (
          <label>
            Days
            <input
              type="number"
              min={5}
              max={252}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </label>
        )}

        {source === "custom" && (
          <label>
            P&L Series (one per line or comma-separated)
            <textarea
              rows={8}
              value={customPnl}
              onChange={(e) => setCustomPnl(e.target.value)}
              placeholder="72.44&#10;-64.06&#10;-73.77"
            />
          </label>
        )}

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button className="primary" onClick={generate} disabled={generating}>
            {generating ? "Generating…" : "Generate P&L Series"}
          </button>
          <button
            className="primary"
            onClick={analyze}
            disabled={analyzing || (source !== "custom" && !customPnl && false)}
            style={{ background: "linear-gradient(135deg, rgb(var(--brand-500)), rgb(var(--brand-400)))", borderColor: "rgb(var(--brand-400))" }}
          >
            {analyzing ? "Analyzing…" : "Run Full Analysis"}
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {result && (
          <div className="metric-grid" style={{ marginTop: "1rem" }}>
            <div className="metric">
              <span className="metric-label">VaR</span>
              <span className="metric-value">${result.var.toLocaleString()}</span>
            </div>
            <div className="metric">
              <span className="metric-label">CVaR</span>
              <span className="metric-value">${result.cvar.toLocaleString()}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Stress Loss</span>
              <span className="metric-value">${result.stressLoss.toLocaleString()}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Stressed Exposure</span>
              <span className="metric-value">${result.stressedExposure.toLocaleString()}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Expected Loss</span>
              <span className="metric-value">${result.expectedLoss.toLocaleString()}</span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
