import { useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";
import { api } from "../../lib/creditApi";
import type { RiskRegime, StressResult, VaRResponse, CVaRResponse, ExpectedLossResponse, ScenarioRunResponse } from "../../types/credit";
import MetricGrid from "./MetricGrid";
import ScenarioBuilder from "./ScenarioBuilder";
import { useScenarioState } from "../../hooks/useScenarioState";

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Filler, Tooltip, Legend);

type QuantTab = "stress" | "var" | "cvar" | "expected_loss" | "composite";

const TABS: { id: QuantTab; label: string }[] = [
  { id: "stress", label: "Stress" },
  { id: "var", label: "VaR" },
  { id: "cvar", label: "CVaR" },
  { id: "expected_loss", label: "Expected Loss" },
  { id: "composite", label: "Composite" },
];

function ResultCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card animate-fade-in">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function PnlDistributionChart({ pnl, varValue: _varValue, cvarValue: _cvarValue }: { pnl: number[]; varValue: number; cvarValue: number }) {
  if (!pnl || pnl.length === 0) return null;

  const sorted = [...pnl].sort((a: number, b: number) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const binCount = Math.min(20, Math.max(5, Math.ceil(Math.sqrt(pnl.length))));
  const binWidth = (max - min) / binCount || 1;
  const bins: number[] = Array(binCount).fill(0);
  const binLabels: string[] = [];

  for (let i = 0; i < binCount; i++) {
    const low = min + i * binWidth;
    const high = low + binWidth;
    binLabels.push(`$${low.toFixed(0)}`);
    bins[i] = pnl.filter((v: number) => v >= low && (i === binCount - 1 ? v <= high : v < high)).length;
  }

  const data = {
    labels: binLabels,
    datasets: [
      {
        label: "Frequency",
        data: bins,
        backgroundColor: "rgba(88, 166, 255, 0.6)",
        borderColor: "rgba(88, 166, 255, 1)",
        borderWidth: 1,
        barPercentage: 1.0,
        categoryPercentage: 1.0,
      },
    ],
  };

  return (
    <div className="chart-container tall">
      <Bar
        data={data}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx: { raw?: unknown }) => `${String(ctx.raw ?? 0)} observations`,
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              title: { display: true, text: "Count", color: "#8b949e" },
              ticks: { color: "#8b949e" },
              grid: { color: "#30363d" },
            },
            x: {
              ticks: { color: "#8b949e", maxRotation: 45 },
              grid: { display: false },
              title: { display: true, text: "P&L (USD)", color: "#8b949e" },
            },
          },
        }}
      />
    </div>
  );
}

export default function QuantTab() {
  const [tab, setTab] = useState<QuantTab>("stress");

  const scenario = useScenarioState("high_volatility");

  // Legacy per-tab state (kept for backward-compatible detail views)
  const [baseExposure, setBaseExposure] = useState(1_000_000);
  const [shockPct, setShockPct] = useState(-0.2);
  const [recoveryRate, setRecoveryRate] = useState(0.4);

  const [stressResult, setStressResult] = useState<StressResult | null>(null);
  const [stressError, setStressError] = useState<string | null>(null);
  const [stressBusy, setStressBusy] = useState(false);

  const [varResult, setVarResult] = useState<VaRResponse | null>(null);
  const [cvarResult, setCvarResult] = useState<CVaRResponse | null>(null);
  const [quantError, setQuantError] = useState<string | null>(null);
  const [quantBusy, setQuantBusy] = useState(false);

  const [elExposure, setElExposure] = useState(500_000);
  const [elPd, setElPd] = useState(0.05);
  const [elLgd, setElLgd] = useState(0.4);
  const [elResult, setElResult] = useState<ExpectedLossResponse | null>(null);
  const [elError, setElError] = useState<string | null>(null);
  const [elBusy, setElBusy] = useState(false);

  const [composite, setComposite] = useState<ScenarioRunResponse | null>(null);
  const [compositeError, setCompositeError] = useState<string | null>(null);
  const [compositeBusy, setCompositeBusy] = useState(false);

  async function runStress() {
    setStressBusy(true);
    setStressError(null);
    try {
      const result = await api.stress(baseExposure, shockPct, recoveryRate);
      setStressResult(result);
    } catch (e) {
      setStressError(e instanceof Error ? e.message : String(e));
    } finally {
      setStressBusy(false);
    }
  }

  async function runVaR() {
    if (scenario.pnl.length === 0) {
      setQuantError("Generate or provide a P&L series first");
      return;
    }
    setQuantBusy(true);
    setQuantError(null);
    try {
      const result = await api.var(scenario.pnl, scenario.confidence);
      setVarResult(result);
    } catch (e) {
      setQuantError(e instanceof Error ? e.message : String(e));
    } finally {
      setQuantBusy(false);
    }
  }

  async function runCVaR() {
    if (scenario.pnl.length === 0) {
      setQuantError("Generate or provide a P&L series first");
      return;
    }
    setQuantBusy(true);
    setQuantError(null);
    try {
      const result = await api.cvar(scenario.pnl, scenario.confidence);
      setCvarResult(result);
    } catch (e) {
      setQuantError(e instanceof Error ? e.message : String(e));
    } finally {
      setQuantBusy(false);
    }
  }

  async function runExpectedLoss() {
    setElBusy(true);
    setElError(null);
    try {
      const result = await api.expectedLoss(elExposure, elPd, elLgd);
      setElResult(result);
    } catch (e) {
      setElError(e instanceof Error ? e.message : String(e));
    } finally {
      setElBusy(false);
    }
  }

  async function runComposite() {
    setCompositeBusy(true);
    setCompositeError(null);
    try {
      const result = await api.runScenario({
        name: `composite_${scenario.regime}`,
        shock_pct: shockPct,
        vix: scenario.regime === "crisis" ? 45 : scenario.regime === "systemic_stress" ? 55 : 25,
      });
      setComposite(result);
    } catch (e) {
      setCompositeError(e instanceof Error ? e.message : String(e));
    } finally {
      setCompositeBusy(false);
    }
  }

  const stressChartData = stressResult
    ? {
        labels: ["Base Exposure", "Stressed Exposure", "Stressed Loss", "Recovery"],
        datasets: [
          {
            label: "USD",
            data: [
              baseExposure,
              stressResult.outputs.stressed_exposure,
              stressResult.outputs.stressed_loss,
              baseExposure * recoveryRate,
            ],
            backgroundColor: [
              "rgba(88, 166, 255, 0.7)",
              "rgba(248, 81, 73, 0.7)",
              "rgba(210, 153, 34, 0.7)",
              "rgba(63, 185, 80, 0.7)",
            ],
            borderColor: [
              "rgba(88, 166, 255, 1)",
              "rgba(248, 81, 73, 1)",
              "rgba(210, 153, 34, 1)",
              "rgba(63, 185, 80, 1)",
            ],
            borderWidth: 1,
          },
        ],
      }
    : null;

  const elChartData = elResult
    ? {
        labels: ["EAD", "Expected Loss", "Recovery Value"],
        datasets: [
          {
            label: "USD",
            data: [elExposure, elResult.outputs.expected_loss, elExposure - elResult.outputs.expected_loss],
            backgroundColor: [
              "rgba(88, 166, 255, 0.7)",
              "rgba(248, 81, 73, 0.7)",
              "rgba(63, 185, 80, 0.7)",
            ],
            borderColor: [
              "rgba(88, 166, 255, 1)",
              "rgba(248, 81, 73, 1)",
              "rgba(63, 185, 80, 1)",
            ],
            borderWidth: 1,
          },
        ],
      }
    : null;

  const compositeChartData = composite
    ? {
        labels: ["Stressed Exposure", "Stressed Loss", "VIX"],
        datasets: [
          {
            label: "Value",
            data: [composite.stressed.outputs.stressed_exposure, composite.stressed.outputs.stressed_loss, composite.vix * 10000],
            backgroundColor: [
              "rgba(88, 166, 255, 0.7)",
              "rgba(248, 81, 73, 0.7)",
              "rgba(210, 153, 34, 0.7)",
            ],
            borderColor: [
              "rgba(88, 166, 255, 1)",
              "rgba(248, 81, 73, 1)",
              "rgba(210, 153, 34, 1)",
            ],
            borderWidth: 1,
          },
        ],
      }
    : null;

  const varChartData = varResult && scenario.pnl.length > 0
    ? {
        labels: scenario.pnl.map((_, i) => `Obs ${i + 1}`),
        datasets: [
          {
            label: "P&L",
            data: scenario.pnl,
            borderColor: "rgba(88, 166, 255, 1)",
            backgroundColor: "rgba(88, 166, 255, 0.1)",
            fill: true,
            tension: 0.1,
          },
          {
            label: `VaR (${(scenario.confidence * 100).toFixed(0)}%)`,
            data: Array(scenario.pnl.length).fill(varResult.outputs.var),
            borderColor: "rgba(248, 81, 73, 1)",
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false,
          },
        ],
      }
    : null;

  return (
    <div className="stack">
      <ScenarioBuilder
        source={scenario.source}
        setSource={scenario.setSource}
        borrowerId={scenario.borrowerId}
        setBorrowerId={scenario.setBorrowerId}
        regime={scenario.regime}
        setRegime={scenario.setRegime}
        exposure={scenario.exposure}
        setExposure={scenario.setExposure}
        confidence={scenario.confidence}
        setConfidence={scenario.setConfidence}
        days={scenario.days}
        setDays={scenario.setDays}
        customPnl={scenario.customPnl}
        setCustomPnl={scenario.setCustomPnl}
        generating={scenario.generating}
        analyzing={scenario.analyzing}
        error={scenario.error}
        result={scenario.result}
        borrowers={scenario.borrowers}
        generate={scenario.generate}
        analyze={scenario.analyze}
        applyPreset={scenario.applyPreset}
        SOURCES={scenario.SOURCES}
        REGIMES={scenario.REGIMES}
        SAMPLE_PRESETS={scenario.SAMPLE_PRESETS}
      />

      {scenario.pnl.length > 0 && (
        <section className="card animate-fade-in">
          <h3>P&L Distribution</h3>
          <p className="muted">
            {scenario.pnl.length} observations · Min ${scenario.pnl.reduce((a, b) => Math.min(a, b), 0).toLocaleString()} · Max ${scenario.pnl.reduce((a, b) => Math.max(a, b), 0).toLocaleString()}
          </p>
          <PnlDistributionChart
            pnl={scenario.pnl}
            varValue={scenario.result?.var ?? 0}
            cvarValue={scenario.result?.cvar ?? 0}
          />
        </section>
      )}

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "stress" && (
        <div className="stack">
          <section className="card">
            <h2>Stress Test</h2>
            <p className="muted">
              Apply a deterministic shock to exposure and view stressed loss.
            </p>
            <label>
              Market regime (display)
              <select value={scenario.regime} onChange={(e) => scenario.setRegime(e.target.value as RiskRegime)}>
                {scenario.REGIMES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </label>
            <label>
              Base exposure (USD)
              <input
                type="number"
                min={0}
                step="any"
                value={baseExposure}
                onChange={(e) => setBaseExposure(Number(e.target.value))}
              />
            </label>
            <label>
              Shock % (delta)
              <input
                type="number"
                min={-0.5}
                max={0.5}
                step="0.01"
                value={shockPct}
                onChange={(e) => setShockPct(Number(e.target.value))}
              />
            </label>
            <label>
              Recovery rate (0–1)
              <input
                type="number"
                min={0}
                max={1}
                step="0.05"
                value={recoveryRate}
                onChange={(e) => setRecoveryRate(Number(e.target.value))}
              />
            </label>
            <button
              className="primary"
              onClick={runStress}
              disabled={stressBusy || baseExposure <= 0}
            >
              {stressBusy ? "Running…" : "Run Stress Test"}
            </button>
          </section>

          {stressError && <p className="error">{stressError}</p>}

          {stressResult && (
            <ResultCard title="Stress Result">
              {stressChartData && (
                <div className="chart-container">
                  <Bar
                    data={stressChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: { legend: { display: false } },
                      scales: {
                        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
                        x: { ticks: { color: "#8b949e" }, grid: { display: false } },
                      },
                    }}
                  />
                </div>
              )}
              <MetricGrid
                items={[
                  ["Stressed Exposure", `${stressResult.outputs.stressed_exposure.toLocaleString()} USD`],
                  ["Stressed Loss", `${stressResult.outputs.stressed_loss.toLocaleString()} USD`],
                  ["Shock", `${(shockPct * 100).toFixed(0)}%`],
                  ["Recovery", `${(recoveryRate * 100).toFixed(0)}%`],
                ]}
              />
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(stressResult, null, 2)}</pre>
              </details>
            </ResultCard>
          )}
        </div>
      )}

      {tab === "var" && (
        <div className="stack">
          <section className="card">
            <h2>Historical Value at Risk (VaR)</h2>
            <p className="muted">
              Compute VaR at a given confidence level from historical P&L observations.
            </p>
            <label>
              Confidence
              <input
                type="number"
                min={0.5}
                max={0.99}
                step="0.01"
                value={scenario.confidence}
                onChange={(e) => scenario.setConfidence(Number(e.target.value))}
              />
            </label>
            <button
              className="primary"
              onClick={runVaR}
              disabled={quantBusy || scenario.pnl.length === 0}
            >
              {quantBusy ? "Computing…" : "Compute VaR"}
            </button>
          </section>

          {quantError && <p className="error">{quantError}</p>}

          {varResult && (
            <ResultCard title="VaR Result">
              {varChartData && (
                <div className="chart-container tall">
                  <Line
                    data={varChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: { legend: { labels: { color: "#8b949e" } } },
                      scales: {
                        y: { ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
                        x: { ticks: { color: "#8b949e" }, grid: { display: false } },
                      },
                    }}
                  />
                </div>
              )}
              <MetricGrid
                items={[
                  ["VaR", `${varResult.outputs.var.toLocaleString()} USD`],
                  ["Confidence", `${(scenario.confidence * 100).toFixed(0)}%`],
                  ["Observations", String(varResult.inputs.pnl_count)],
                ]}
              />
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(varResult, null, 2)}</pre>
              </details>
            </ResultCard>
          )}
        </div>
      )}

      {tab === "cvar" && (
        <div className="stack">
          <section className="card">
            <h2>Historical CVaR / Expected Shortfall</h2>
            <p className="muted">
              Compute tail-loss expectation beyond VaR at a given confidence level.
            </p>
            <label>
              Confidence
              <input
                type="number"
                min={0.5}
                max={0.99}
                step="0.01"
                value={scenario.confidence}
                onChange={(e) => scenario.setConfidence(Number(e.target.value))}
              />
            </label>
            <button
              className="primary"
              onClick={runCVaR}
              disabled={quantBusy || scenario.pnl.length === 0}
            >
              {quantBusy ? "Computing…" : "Compute CVaR"}
            </button>
          </section>

          {quantError && <p className="error">{quantError}</p>}

          {cvarResult && (
            <ResultCard title="CVaR Result">
              <MetricGrid
                items={[
                  ["CVaR", `${cvarResult.outputs.cvar.toLocaleString()} USD`],
                  ["Confidence", `${(scenario.confidence * 100).toFixed(0)}%`],
                  ["Observations", String(cvarResult.inputs.pnl_count)],
                ]}
              />
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(cvarResult, null, 2)}</pre>
              </details>
            </ResultCard>
          )}
        </div>
      )}

      {tab === "expected_loss" && (
        <div className="stack">
          <section className="card">
            <h2>Expected Loss (EL)</h2>
            <p className="muted">
              Compute EL = EAD × PD × LGD.
            </p>
            <label>
              Exposure at Default (USD)
              <input
                type="number"
                min={0}
                step="any"
                value={elExposure}
                onChange={(e) => setElExposure(Number(e.target.value))}
              />
            </label>
            <label>
              Probability of Default (0–1)
              <input
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={elPd}
                onChange={(e) => setElPd(Number(e.target.value))}
              />
            </label>
            <label>
              Loss Given Default (0–1)
              <input
                type="number"
                min={0}
                max={1}
                step="0.05"
                value={elLgd}
                onChange={(e) => setElLgd(Number(e.target.value))}
              />
            </label>
            <button
              className="primary"
              onClick={runExpectedLoss}
              disabled={elBusy}
            >
              {elBusy ? "Computing…" : "Compute Expected Loss"}
            </button>
          </section>

          {elError && <p className="error">{elError}</p>}

          {elResult && (
            <ResultCard title="Expected Loss Result">
              {elChartData && (
                <div className="chart-container">
                  <Bar
                    data={elChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: { legend: { display: false } },
                      scales: {
                        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
                        x: { ticks: { color: "#8b949e" }, grid: { display: false } },
                      },
                    }}
                  />
                </div>
              )}
              <MetricGrid
                items={[
                  ["Expected Loss", `${elResult.outputs.expected_loss.toLocaleString()} USD`],
                  ["EAD", `${elExposure.toLocaleString()} USD`],
                  ["PD", `${(elPd * 100).toFixed(2)}%`],
                  ["LGD", `${(elLgd * 100).toFixed(0)}%`],
                ]}
              />
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(elResult, null, 2)}</pre>
              </details>
            </ResultCard>
          )}
        </div>
      )}

      {tab === "composite" && (
        <div className="stack">
          <section className="card">
            <h2>Composite Scenario</h2>
            <p className="muted">
              Run all deterministic scenario metrics for a single exposure.
            </p>
            <label>
              Market regime (display)
              <select value={scenario.regime} onChange={(e) => scenario.setRegime(e.target.value as RiskRegime)}>
                {scenario.REGIMES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </label>
            <label>
              Shock % (delta)
              <input
                type="number"
                min={-0.5}
                max={0.5}
                step="0.01"
                value={shockPct}
                onChange={(e) => setShockPct(Number(e.target.value))}
              />
            </label>
            <button
              className="primary"
              onClick={runComposite}
              disabled={compositeBusy}
            >
              {compositeBusy ? "Running…" : "Run Composite Scenario"}
            </button>
          </section>

          {compositeError && <p className="error">{compositeError}</p>}

          {composite && (
            <ResultCard title="Composite Scenario Result">
              {compositeChartData && (
                <div className="chart-container">
                  <Bar
                    data={compositeChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: { legend: { display: false } },
                      scales: {
                        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#30363d" } },
                        x: { ticks: { color: "#8b949e" }, grid: { display: false } },
                      },
                    }}
                  />
                </div>
              )}
              <MetricGrid
                items={[
                  ["Scenario", composite.scenario],
                  ["Label", composite.label],
                  ["Shock", `${(composite.shock_pct * 100).toFixed(0)}%`],
                  ["VIX", String(composite.vix)],
                  ["Stressed Exposure", `${composite.stressed.outputs.stressed_exposure.toLocaleString()} USD`],
                  ["Stressed Loss", `${composite.stressed.outputs.stressed_loss.toLocaleString()} USD`],
                ]}
              />
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(composite, null, 2)}</pre>
              </details>
            </ResultCard>
          )}
        </div>
      )}
    </div>
  );
}
