import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";
import { api } from "../../lib/creditApi";
import type {
  ContagionResponse,
  CounterpartyExposureResponse,
  PortfolioExposureResponse,
  PortfolioVarResponse,
  SystemicStressResponse,
} from "../../types/credit";
import MetricGrid from "./MetricGrid";

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Tooltip, Legend);

type PortfolioSection = "exposure" | "stress" | "contagion" | "var" | "counterparty";

const SECTIONS: { id: PortfolioSection; label: string }[] = [
  { id: "exposure", label: "Exposure" },
  { id: "stress", label: "Systemic Stress" },
  { id: "contagion", label: "Contagion" },
  { id: "var", label: "Portfolio VaR" },
  { id: "counterparty", label: "Counterparty" },
];

export default function PortfolioTab() {
  const [section, setSection] = useState<PortfolioSection>("exposure");

  const [borrowers, setBorrowers] = useState<string[]>([]);
  const [loadingBorrowers, setLoadingBorrowers] = useState(false);

  const [exposure, setExposure] = useState<PortfolioExposureResponse | null>(null);
  const [exposureError, setExposureError] = useState<string | null>(null);
  const [exposureBusy, setExposureBusy] = useState(false);

  const [stress, setStress] = useState<SystemicStressResponse | null>(null);
  const [stressError, setStressError] = useState<string | null>(null);
  const [stressBusy, setStressBusy] = useState(false);
  const [stressShock, setStressShock] = useState(-0.55);

  const [contagionBorrower, setContagionBorrower] = useState("");
  const [contagionShock, setContagionShock] = useState(0.25);
  const [contagion, setContagion] = useState<ContagionResponse | null>(null);
  const [contagionError, setContagionError] = useState<string | null>(null);
  const [contagionBusy, setContagionBusy] = useState(false);

  const [varConfidence, setVarConfidence] = useState(0.95);
  const [portfolioVar, setPortfolioVar] = useState<PortfolioVarResponse | null>(null);
  const [varError, setVarError] = useState<string | null>(null);
  const [varBusy, setVarBusy] = useState(false);

  const [cpProtocol, setCpProtocol] = useState("");
  const [counterparty, setCounterparty] = useState<CounterpartyExposureResponse | null>(null);
  const [cpError, setCpError] = useState<string | null>(null);
  const [cpBusy, setCpBusy] = useState(false);

  useEffect(() => {
    setLoadingBorrowers(true);
    api.listBorrowers()
      .then(setBorrowers)
      .catch(() => {})
      .finally(() => setLoadingBorrowers(false));
  }, []);

  async function runExposure() {
    setExposureBusy(true);
    setExposureError(null);
    try {
      const result = await api.portfolioExposure();
      setExposure(result);
    } catch (e) {
      setExposureError(e instanceof Error ? e.message : String(e));
    } finally {
      setExposureBusy(false);
    }
  }

  async function runSystemicStress() {
    setStressBusy(true);
    setStressError(null);
    try {
      const result = await api.systemicStress(stressShock);
      setStress(result);
    } catch (e) {
      setStressError(e instanceof Error ? e.message : String(e));
    } finally {
      setStressBusy(false);
    }
  }

  async function runContagion() {
    if (!contagionBorrower) return;
    setContagionBusy(true);
    setContagionError(null);
    try {
      const result = await api.contagionAnalysis(contagionBorrower, contagionShock);
      setContagion(result);
    } catch (e) {
      setContagionError(e instanceof Error ? e.message : String(e));
    } finally {
      setContagionBusy(false);
    }
  }

  async function runPortfolioVar() {
    setVarBusy(true);
    setVarError(null);
    try {
      const result = await api.portfolioVar(varConfidence);
      setPortfolioVar(result);
    } catch (e) {
      setVarError(e instanceof Error ? e.message : String(e));
    } finally {
      setVarBusy(false);
    }
  }

  async function runCounterparty() {
    if (!cpProtocol) return;
    setCpBusy(true);
    setCpError(null);
    try {
      const result = await api.counterpartyExposure(cpProtocol);
      setCounterparty(result);
    } catch (e) {
      setCpError(e instanceof Error ? e.message : String(e));
    } finally {
      setCpBusy(false);
    }
  }

  const exposureChartData = exposure
    ? {
        labels: exposure.outputs.protocols.map((p) => p.protocol),
        datasets: [
          {
            label: "Exposure (USD)",
            data: exposure.outputs.protocols.map((p) => p.total_exposure),
            backgroundColor: [
              "rgba(63, 185, 80, 0.7)",
              "rgba(88, 166, 255, 0.7)",
              "rgba(210, 153, 34, 0.7)",
              "rgba(248, 81, 73, 0.7)",
              "rgba(139, 148, 158, 0.7)",
              "rgba(163, 113, 247, 0.7)",
            ],
            borderColor: [
              "rgba(63, 185, 80, 1)",
              "rgba(88, 166, 255, 1)",
              "rgba(210, 153, 34, 1)",
              "rgba(248, 81, 73, 1)",
              "rgba(139, 148, 158, 1)",
              "rgba(163, 113, 247, 1)",
            ],
            borderWidth: 1,
          },
        ],
      }
    : null;

  const stressChartData = stress
    ? {
        labels: ["Base Collateral", "Stressed Collateral", "Collateral Loss"],
        datasets: [
          {
            label: "USD",
            data: [stress.outputs.base_collateral, stress.outputs.stressed_collateral, stress.outputs.total_collateral_loss],
            backgroundColor: [
              "rgba(88, 166, 255, 0.7)",
              "rgba(210, 153, 34, 0.7)",
              "rgba(248, 81, 73, 0.7)",
            ],
            borderColor: [
              "rgba(88, 166, 255, 1)",
              "rgba(210, 153, 34, 1)",
              "rgba(248, 81, 73, 1)",
            ],
            borderWidth: 1,
          },
        ],
      }
    : null;

  const cpChartData = counterparty
    ? {
        labels: counterparty.outputs.borrowers.map((b) => b.borrower_id),
        datasets: [
          {
            label: "Protocol Exposure (USD)",
            data: counterparty.outputs.borrowers.map((b) => b.protocol_exposure),
            backgroundColor: "rgba(88, 166, 255, 0.7)",
            borderColor: "rgba(88, 166, 255, 1)",
            borderWidth: 1,
          },
        ],
      }
    : null;

  return (
    <div className="stack">
      <nav className="tabs" role="tablist">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={section === s.id}
            className={`tab ${section === s.id ? "active" : ""}`}
            onClick={() => setSection(s.id)}
          >
            {s.label}
          </button>
        ))}
      </nav>

      {section === "exposure" && (
        <div className="stack">
          <section className="card">
            <h2>Portfolio Exposure (E12)</h2>
            <p className="muted">Aggregate exposure across borrowers and protocols.</p>
            <button className="primary" onClick={runExposure} disabled={exposureBusy}>
              {exposureBusy ? "Loading…" : "Load Portfolio Exposure"}
            </button>
          </section>

          {exposureError && <p className="error">{exposureError}</p>}

          {exposure && (
            <section className="card animate-fade-in">
              <h3>Portfolio Totals</h3>
              <MetricGrid
                items={[
                  ["Total Exposure", `${exposure.outputs.totals.total_exposure.toLocaleString()} USD`],
                  ["Total Collateral", `${exposure.outputs.totals.total_collateral_value.toLocaleString()} USD`],
                  ["Total Liabilities", `${exposure.outputs.totals.total_liabilities.toLocaleString()} USD`],
                  ["Net Exposure", `${exposure.outputs.totals.net_exposure.toLocaleString()} USD`],
                ]}
              />

              {exposureChartData && (
                <div className="chart-container tall">
                  <Doughnut
                    data={exposureChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                        legend: { position: "right", labels: { color: "rgb(var(--slate-400))", padding: 12 } },
                      },
                    }}
                  />
                </div>
              )}

              <h3>Borrower Table</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Borrower</th>
                      <th scope="col">Regime</th>
                      <th scope="col">Collateral</th>
                      <th scope="col">Liabilities</th>
                      <th scope="col">Exposure</th>
                      <th scope="col">Net Worth</th>
                      <th scope="col">Protocols</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exposure.outputs.borrowers.map((b) => (
                      <tr key={b.borrower_id}>
                        <td className="mono">{b.borrower_id}</td>
                        <td>{b.market_regime}</td>
                        <td>${b.total_collateral_value.toLocaleString()}</td>
                        <td>${b.total_liabilities.toLocaleString()}</td>
                        <td>${b.total_exposure.toLocaleString()}</td>
                        <td>${b.net_worth.toLocaleString()}</td>
                        <td>{b.protocols.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>Protocol Concentration</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Protocol</th>
                      <th scope="col">Exposure</th>
                      <th scope="col">Borrowers</th>
                      <th scope="col">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exposure.outputs.protocols.map((p) => (
                      <tr key={p.protocol}>
                        <td>{p.protocol}</td>
                        <td>${p.total_exposure.toLocaleString()}</td>
                        <td>{p.borrower_count}</td>
                        <td>{(p.share_of_portfolio * 100).toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(exposure, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}

      {section === "stress" && (
        <div className="stack">
          <section className="card">
            <h2>Systemic Stress (E12)</h2>
            <p className="muted">Run a portfolio-wide shock and identify insolvent borrowers.</p>
            <label>
              Shock %
              <input
                type="number"
                step="0.01"
                value={stressShock}
                onChange={(e) => setStressShock(Number(e.target.value))}
              />
            </label>
            <button className="primary" onClick={runSystemicStress} disabled={stressBusy}>
              {stressBusy ? "Running…" : "Run Systemic Stress"}
            </button>
          </section>

          {stressError && <p className="error">{stressError}</p>}

          {stress && (
            <section className="card animate-fade-in">
              <h3>Systemic Stress Result</h3>
              {stressChartData && (
                <div className="chart-container">
                  <Bar
                    data={stressChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: { legend: { display: false } },
                      scales: {
                        y: { beginAtZero: true, ticks: { color: "rgb(var(--slate-400))" }, grid: { color: "rgb(var(--slate-700))" } },
                        x: { ticks: { color: "rgb(var(--slate-400))" }, grid: { display: false } },
                      },
                    }}
                  />
                </div>
              )}
              <MetricGrid
                items={[
                  ["Shock", `${(stress.outputs.shock_pct * 100).toFixed(2)}%`],
                  ["Base Collateral", `$${stress.outputs.base_collateral.toLocaleString()}`],
                  ["Stressed Collateral", `$${stress.outputs.stressed_collateral.toLocaleString()}`],
                  ["Total Collateral Loss", `$${stress.outputs.total_collateral_loss.toLocaleString()}`],
                  ["Insolvent Borrowers", String(stress.outputs.insolvent_borrower_count)],
                  ["Severity", stress.outputs.severity],
                ]}
              />

              <h3>Insolvent Borrowers</h3>
              {stress.outputs.insolvent_borrowers.length > 0 ? (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Borrower</th>
                        <th scope="col">Stressed Collateral</th>
                        <th scope="col">Liabilities</th>
                        <th scope="col">Shortfall</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stress.outputs.insolvent_borrowers.map((b) => (
                        <tr key={b.borrower_id}>
                          <td className="mono">{b.borrower_id}</td>
                          <td>${b.stressed_collateral.toLocaleString()}</td>
                          <td>${b.total_liabilities.toLocaleString()}</td>
                          <td className="error">${b.shortfall.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted">No insolvent borrowers at this shock level.</p>
              )}

              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(stress, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}

      {section === "contagion" && (
        <div className="stack">
          <section className="card">
            <h2>Run Contagion</h2>
            <p className="muted">Simulate contagion from a defaulted borrower.</p>
            <label>
              Borrower
              <select
                value={contagionBorrower}
                onChange={(e) => setContagionBorrower(e.target.value)}
                disabled={loadingBorrowers}
              >
                <option value="">-- select a borrower --</option>
                {borrowers.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </label>
            <label>
              Shock %
              <input
                type="number"
                step="0.01"
                value={contagionShock}
                onChange={(e) => setContagionShock(Number(e.target.value))}
              />
            </label>
            <button className="primary" onClick={runContagion} disabled={contagionBusy || !contagionBorrower}>
              {contagionBusy ? "Running…" : "Run Contagion Analysis"}
            </button>
          </section>

          {contagionError && <p className="error">{contagionError}</p>}

          {contagion && (
            <section className="card animate-fade-in">
              <h3>Contagion Result</h3>
              <MetricGrid
                items={[
                  ["Source Borrower", contagion.outputs.source_borrower_id],
                  ["Infected Borrowers", String(contagion.outputs.infected_borrower_count)],
                  ["Defaulted Borrowers", String(contagion.outputs.defaulted_borrower_count)],
                  ["Cascade Depth", String(contagion.outputs.cascade_depth)],
                  ["Primary Collateral Loss", `$${contagion.outputs.primary_collateral_loss.toLocaleString()}`],
                  ["Contagion Collateral Loss", `$${contagion.outputs.contagion_collateral_loss.toLocaleString()}`],
                  ["Total Collateral Loss", `$${contagion.outputs.total_collateral_loss.toLocaleString()}`],
                  ["Portfolio Loss Share", `${(contagion.outputs.loss_as_share_of_portfolio * 100).toFixed(2)}%`],
                  ["Severity", contagion.outputs.severity],
                ]}
              />

              {contagion.outputs.defaulted_borrowers.length > 0 && (
                <>
                  <h3>Defaulted Borrowers</h3>
                  <ul>
                    {contagion.outputs.defaulted_borrowers.map((b) => (
                      <li key={b} className="mono">{b}</li>
                    ))}
                  </ul>
                </>
              )}

              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(contagion, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}

      {section === "var" && (
        <div className="stack">
          <section className="card">
            <h2>Portfolio VaR</h2>
            <p className="muted">Compute Value at Risk for the portfolio.</p>
            <label>
              Confidence
              <input
                type="number"
                min={0.5}
                max={0.99}
                step="0.01"
                value={varConfidence}
                onChange={(e) => setVarConfidence(Number(e.target.value))}
              />
            </label>
            <button className="primary" onClick={runPortfolioVar} disabled={varBusy}>
              {varBusy ? "Computing…" : "Compute Portfolio VaR"}
            </button>
          </section>

          {varError && <p className="error">{varError}</p>}

          {portfolioVar && (
            <section className="card animate-fade-in">
              <h3>VaR Result</h3>
              <MetricGrid
                items={[
                  ["VaR", `${portfolioVar.outputs.var.toLocaleString()} USD`],
                  ["VaR % of Portfolio", `${portfolioVar.outputs.var_pct_of_portfolio.toFixed(2)}%`],
                  ["Confidence", `${(varConfidence * 100).toFixed(0)}%`],
                  ["Z Score", portfolioVar.outputs.z_score.toFixed(4)],
                  ["Portfolio Value", `$${portfolioVar.outputs.portfolio_value.toLocaleString()}`],
                  ["Annual Volatility", `${(portfolioVar.outputs.portfolio_volatility_annual * 100).toFixed(2)}%`],
                  ["Horizon Volatility", `${(portfolioVar.outputs.portfolio_volatility_horizon * 100).toFixed(2)}%`],
                ]}
              />

              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(portfolioVar, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}

      {section === "counterparty" && (
        <div className="stack">
          <section className="card">
            <h2>Counterparty Exposure</h2>
            <p className="muted">Inspect exposure concentration for a specific protocol.</p>
            <label>
              Protocol
              <input
                type="text"
                value={cpProtocol}
                onChange={(e) => setCpProtocol(e.target.value)}
                placeholder="e.g. Aave, Compound"
              />
            </label>
            <button className="primary" onClick={runCounterparty} disabled={cpBusy || !cpProtocol}>
              {cpBusy ? "Loading…" : "Load Counterparty Exposure"}
            </button>
          </section>

          {cpError && <p className="error">{cpError}</p>}

          {counterparty && (
            <section className="card animate-fade-in">
              <h3>Counterparty Exposure</h3>
              <MetricGrid
                items={[
                  ["Protocol", counterparty.outputs.protocol],
                  ["Total Exposure", `$${counterparty.outputs.total_exposure.toLocaleString()}`],
                  ["Borrower Count", String(counterparty.outputs.borrower_count)],
                  ["Share of Portfolio", `${(counterparty.outputs.share_of_portfolio * 100).toFixed(2)}%`],
                  ["Risk Level", counterparty.outputs.risk_level],
                ]}
              />

              {cpChartData && (
                <div className="chart-container" style={{ marginTop: "1rem" }}>
                  <Bar
                    data={cpChartData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      indexAxis: "y",
                      plugins: { legend: { display: false } },
                      scales: {
                        x: { beginAtZero: true, ticks: { color: "rgb(var(--slate-400))" }, grid: { color: "rgb(var(--slate-700))" } },
                        y: { ticks: { color: "rgb(var(--slate-400))" }, grid: { display: false } },
                      },
                    }}
                  />
                </div>
              )}

              <h3>Borrowers</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Borrower</th>
                      <th scope="col">Regime</th>
                      <th scope="col">Protocol Exposure</th>
                      <th scope="col">Total Exposure</th>
                      <th scope="col">Exposure Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {counterparty.outputs.borrowers.map((b) => (
                      <tr key={b.borrower_id}>
                        <td className="mono">{b.borrower_id}</td>
                        <td>{b.market_regime}</td>
                        <td>${b.protocol_exposure.toLocaleString()}</td>
                        <td>${b.borrower_total_exposure.toLocaleString()}</td>
                        <td>{(b.exposure_share * 100).toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(counterparty, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
