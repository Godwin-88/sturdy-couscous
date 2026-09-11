import { useEffect, useRef, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar } from "react-chartjs-2";
import { api } from "../../lib/creditApi";
import type {
  BayesianUpdateResponse,
  CreditAssessment,
  CreditDecision,
  CreditExecution,
  DecisionReconstructResponse,
  ExecutionAccountResponse,
  RiskRegime,
  WalletExposureResponse,
  WalletResolveResponse,
} from "../../types/credit";
import MetricGrid from "./MetricGrid";
import { StepIndicator } from "./StepIndicator";
import { DemoModeButton } from "./DemoModeButton";
import { showToast } from "./Toast";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend
);

const REGIMES: RiskRegime[] = [
  "trending",
  "mean_reverting",
  "high_volatility",
  "low_volatility",
  "crisis",
  "systemic_stress",
  "recovery",
  "neutral",
];

export default function CreditDashboard() {
  const [borrowerId, setBorrowerId] = useState("");
  const [borrowers, setBorrowers] = useState<string[]>([]);
  const [loadingBorrowers, setLoadingBorrowers] = useState(false);
  const [requestedAmount, setRequestedAmount] = useState(100);
  const [regime, setRegime] = useState<RiskRegime>("high_volatility");
  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<CreditAssessment | null>(null);
  const [decision, setDecision] = useState<CreditDecision | null>(null);
  const [execution, setExecution] = useState<CreditExecution | null>(null);
  const [executionAccount, setExecutionAccount] = useState<ExecutionAccountResponse | null>(null);
  const [monitorStatus, setMonitorStatus] = useState<string | null>(null);
  const [monitoring, setMonitoring] = useState(false);

  const [wallets, setWallets] = useState<WalletResolveResponse[]>([]);
  const [loadingWallets, setLoadingWallets] = useState(false);

  const [reconstruct, setReconstruct] = useState<DecisionReconstructResponse | null>(null);
  const [reconstructError, setReconstructError] = useState<string | null>(null);
  const [reconstructBusy, setReconstructBusy] = useState(false);

  const [overrideReason, setOverrideReason] = useState("");
  const [overrideBy, setOverrideBy] = useState("user");
  const [overrideResult, setOverrideResult] = useState<Record<string, unknown> | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const [overrideBusy, setOverrideBusy] = useState(false);

  const [bayesianPrior, setBayesianPrior] = useState(0.1);
  const [bayesianEvidence, setBayesianEvidence] = useState("attestation,0.8\nliability,0.3");
  const [bayesianResult, setBayesianResult] = useState<BayesianUpdateResponse | null>(null);
  const [bayesianError, setBayesianError] = useState<string | null>(null);
  const [bayesianBusy, setBayesianBusy] = useState(false);

  const [demoStep, setDemoStep] = useState(0);
  const [demoDone, setDemoDone] = useState<Set<number>>(new Set());

  const monitorIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.executionAccount().then(setExecutionAccount).catch(() => {});
  }, []);

  useEffect(() => {
    setLoadingBorrowers(true);
    api.listBorrowers()
      .then(setBorrowers)
      .catch(() => {})
      .finally(() => setLoadingBorrowers(false));
  }, []);

  useEffect(() => {
    return () => {
      if (monitorIntervalRef.current) {
        clearInterval(monitorIntervalRef.current);
      }
    };
  }, []);

  async function seedAndDecide() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.seedDemoBorrower();
      const refreshed = await api.listBorrowers();
      setBorrowers(refreshed);
      setBorrowerId("borrower_demo_alice");
      const decided = await api.decide("borrower_demo_alice", {
        requested_amount: requestedAmount,
        regime,
      });
      setDecision(decided);
      setAssessment({
        borrower_id: decided.borrower_id,
        credit_score: decided.credit_score,
        probability_of_default: decided.probability_of_default,
        expected_loss: decided.expected_loss,
        loan_to_value: decided.collateral_value > 0 ? requestedAmount / decided.collateral_value : 0,
        required_collateral_ratio: decided.required_collateral_ratio,
        stress_ltv: decided.stress_result,
        market_regime: decided.risk_regime,
        principal_risk_factors: decided.principal_risk_factors,
        models: decided.model_versions,
        created_at: decided.created_at,
      });
      setNotice("Demo borrower seeded; recommendation generated.");
      setDemoStep(1);
      setDemoDone((s) => new Set(s).add(0));
      showToast("Demo borrower created and assessed", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      showToast("Failed to seed demo borrower", "error");
    } finally {
      setBusy(false);
    }
  }

  async function evaluateExisting() {
    if (!borrowerId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const decided = await api.decide(borrowerId, {
        requested_amount: requestedAmount,
        regime,
      });
      setDecision(decided);
      setAssessment({
        borrower_id: decided.borrower_id,
        credit_score: decided.credit_score,
        probability_of_default: decided.probability_of_default,
        expected_loss: decided.expected_loss,
        loan_to_value: decided.collateral_value > 0 ? requestedAmount / decided.collateral_value : 0,
        required_collateral_ratio: decided.required_collateral_ratio,
        stress_ltv: decided.stress_result,
        market_regime: decided.risk_regime,
        principal_risk_factors: decided.principal_risk_factors,
        models: decided.model_versions,
        created_at: decided.created_at,
      });
      setNotice("Recommendation generated for existing borrower.");
      setDemoStep(1);
      setDemoDone((s) => new Set(s).add(0));
      showToast("Assessment complete", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      showToast("Assessment failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function runFullDemo() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await seedAndDecide();
      await new Promise((r) => setTimeout(r, 500));
      await loadWallets();
      await new Promise((r) => setTimeout(r, 300));
      await runBayesian();
      setDemoStep(2);
      setDemoDone((s) => new Set(s).add(1));
      showToast("Full demo pipeline complete", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
      showToast("Demo pipeline failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function approveAndExecute() {
    if (!decision) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.approveDecision(decision.decision_id);
      setNotice("Decision approved — human operator in the loop.");
      const exec = await api.execute({
        decision_id: decision.decision_id,
        to: recipient,
      });
      setExecution(exec);
      startMonitoring(exec.tx_hash);
      setDemoStep(3);
      setDemoDone((s) => new Set(s).add(2));
      showToast("Decision executed on-chain", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      showToast("Execution failed", "error");
    } finally {
      setBusy(false);
    }
  }

  function startMonitoring(txHash: string | null) {
    if (!txHash) return;
    setMonitoring(true);
    setMonitorStatus("Monitoring on-chain status…");

    const poll = async () => {
      try {
        const data = await api.monitor(txHash);
        const status = (data as { status?: string }).status ?? "unknown";
        setMonitorStatus(status);
        if (["finalized", "failed", "timeout"].includes(status)) {
          setMonitoring(false);
          if (monitorIntervalRef.current) {
            clearInterval(monitorIntervalRef.current);
            monitorIntervalRef.current = null;
          }
        }
      } catch {
        setMonitorStatus("poll_error");
      }
    };

    poll();
    monitorIntervalRef.current = setInterval(poll, 5000);
  }

  async function loadWallets() {
    if (!borrowerId && !decision) return;
    const targetBorrower = borrowerId || decision?.borrower_id;
    if (!targetBorrower) return;
    setLoadingWallets(true);
    try {
      const data = await api.borrowerWallets(targetBorrower);
      setWallets(data.wallets);
    } catch {
      setWallets([]);
    } finally {
      setLoadingWallets(false);
    }
  }

  async function reconstructDecision() {
    if (!decision) return;
    setReconstructBusy(true);
    setReconstructError(null);
    try {
      const data = await api.reconstructDecision(decision.decision_id);
      setReconstruct(data);
      showToast("Decision provenance reconstructed", "info");
    } catch (e) {
      setReconstructError(e instanceof Error ? e.message : String(e));
      showToast("Reconstruction failed", "error");
    } finally {
      setReconstructBusy(false);
    }
  }

  async function overrideDecisionHandler() {
    if (!decision || !overrideReason.trim()) return;
    setOverrideBusy(true);
    setOverrideError(null);
    try {
      const result = await api.overrideDecision(decision.decision_id, overrideReason.trim());
      setOverrideResult(result as Record<string, unknown>);
      setDecision((d) => {
        if (!d) return d;
        return { ...d, decision_status: "overridden", approval_status: d.approval_status };
      });
      setOverrideReason("");
      showToast("Decision overridden successfully", "success");
    } catch (e) {
      setOverrideError(e instanceof Error ? e.message : String(e));
      showToast("Override failed", "error");
    } finally {
      setOverrideBusy(false);
    }
  }

  async function runBayesian() {
    setBayesianBusy(true);
    setBayesianError(null);
    try {
      const evidence = bayesianEvidence
        .split(/[\n,]+/)
        .map((s) => {
          const [type, strength] = s.split(":");
          return { type: type?.trim() || "attestation", strength: parseFloat(strength?.trim() || "0.5") };
        })
        .filter((e) => e.type);
      const result = await api.bayesianUpdate(bayesianPrior, evidence);
      setBayesianResult(result);
      showToast("Bayesian update complete", "success");
    } catch (e) {
      setBayesianError(e instanceof Error ? e.message : String(e));
      showToast("Bayesian update failed", "error");
    } finally {
      setBayesianBusy(false);
    }
  }

  const approved = decision?.approval_status === "approved";
  const executed = execution?.status === "finalized";

  const walletChains = wallets.reduce<Record<string, number>>((acc, w) => {
    acc[w.chain] = (acc[w.chain] || 0) + 1;
    return acc;
  }, {});
  const chainLabels = Object.keys(walletChains);
  const chainCounts = chainLabels.map((c) => walletChains[c]);

  const walletChartData = {
    labels: chainLabels.length > 0 ? chainLabels : ["No Data"],
    datasets: [
      {
        label: "Wallets",
        data: chainCounts.length > 0 ? chainCounts : [0],
        backgroundColor: [
          "rgba(63, 185, 80, 0.7)",
          "rgba(88, 166, 255, 0.7)",
          "rgba(210, 153, 34, 0.7)",
          "rgba(248, 81, 73, 0.7)",
          "rgba(139, 148, 158, 0.7)",
        ],
        borderColor: [
          "rgba(63, 185, 80, 1)",
          "rgba(88, 166, 255, 1)",
          "rgba(210, 153, 34, 1)",
          "rgba(248, 81, 73, 1)",
          "rgba(139, 148, 158, 1)",
        ],
        borderWidth: 1,
      },
    ],
  };

  const bayesianChartData = bayesianResult
    ? {
        labels: ["Prior PD", "Posterior PD", "CI Lower", "CI Upper"],
        datasets: [
          {
            label: "Probability (%)",
            data: [
              (bayesianResult.inputs as Record<string, number>).prior_pd * 100,
              bayesianResult.outputs.posterior_pd * 100,
              (bayesianResult.outputs.confidence_interval_95 as { lower: number }).lower * 100,
              (bayesianResult.outputs.confidence_interval_95 as { upper: number }).upper * 100,
            ],
            backgroundColor: [
              "rgba(88, 166, 255, 0.7)",
              "rgba(63, 185, 80, 0.7)",
              "rgba(210, 153, 34, 0.7)",
              "rgba(248, 81, 73, 0.7)",
            ],
            borderColor: [
              "rgba(88, 166, 255, 1)",
              "rgba(63, 185, 80, 1)",
              "rgba(210, 153, 34, 1)",
              "rgba(248, 81, 73, 1)",
            ],
            borderWidth: 1,
          },
        ],
      }
    : null;

  return (
    <div className="stack">
      {/* Hero */}
      <section className="hero">
        <h1>Credit Decision Workbench</h1>
        <p>
          Evaluate, decide, and execute verifiable credit decisions across chains with
          transparent provenance.
        </p>
        <DemoModeButton onRunDemo={runFullDemo} busy={busy} />
        <StepIndicator currentStep={demoStep} completedSteps={demoDone} />
      </section>

      {executionAccount && (
        <section className="card animate-fade-in">
          <h3>Execution Service</h3>
          <div className="metric-grid">
            <div className="metric">
              <span className="metric-label">Configured</span>
              <span className={`badge data-status=${executionAccount.configured ? "verified" : "unverified"}`}>
                {executionAccount.configured ? "Yes" : "No"}
              </span>
            </div>
            {executionAccount.address && (
              <div className="metric">
                <span className="metric-label">Executor</span>
                <span className="mono">{executionAccount.address}</span>
              </div>
            )}
            {executionAccount.reason && (
              <div className="metric">
                <span className="metric-label">Reason</span>
                <span className="muted">{executionAccount.reason}</span>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="card">
        <h2>Borrower Evaluation</h2>
        <label>
          Borrower
          <select
            value={borrowerId}
            onChange={(e) => setBorrowerId(e.target.value)}
            disabled={loadingBorrowers}
          >
            <option value="">-- select a borrower --</option>
            {borrowers.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </label>
        <button
          className="secondary"
          onClick={seedAndDecide}
          disabled={busy}
          style={{ marginBottom: "0.75rem" }}
        >
          {busy ? "Working…" : "Seed Demo Borrower"}
        </button>
        <label>
          Requested amount (CTC)
          <input
            type="number"
            min={1}
            value={requestedAmount}
            onChange={(e) => setRequestedAmount(Number(e.target.value))}
          />
        </label>
        <label>
          Market regime
          <select
            value={regime}
            onChange={(e) => setRegime(e.target.value as RiskRegime)}
          >
            {REGIMES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        <button
          className="primary"
          onClick={evaluateExisting}
          disabled={busy || !borrowerId || requestedAmount <= 0}
        >
          {busy ? "Working…" : "Evaluate & Recommend"}
        </button>
      </section>

      {assessment && decision && (
        <>
          <section className="card animate-fade-in">
            <h2>Wallet Discovery (E1)</h2>
            <button className="primary" onClick={loadWallets} disabled={loadingWallets || !borrowerId}>
              {loadingWallets ? "Loading…" : "Load Borrower Wallets"}
            </button>
            {wallets.length > 0 && (
              <div className="data-status" style={{ marginTop: "1rem" }}>
                <div className="chart-container" style={{ height: "auto" }}>
                  <Bar
                    data={walletChartData}
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
                <div className="table-wrap" style={{ marginTop: "1rem" }}>
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Address</th>
                        <th scope="col">Chain</th>
                        <th scope="col">Supported</th>
                        <th scope="col">Assets</th>
                        <th scope="col">Net Worth</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wallets.map((w) => (
                        <tr key={w.address}>
                          <td className="mono">{w.address}</td>
                          <td>{w.chain}</td>
                          <td>{w.supported ? "Yes" : "No"}</td>
                          <td>{w.assets.length}</td>
                          <td>${(w as unknown as WalletExposureResponse).totals?.net_worth?.toLocaleString() ?? "0"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>

          <section className="card animate-fade-in">
            <h2>Bayesian Risk Update (E5-US2)</h2>
            <p className="muted">Update PD with evidence using Beta-binomial conjugate prior.</p>
            <label>
              Prior PD
              <input
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={bayesianPrior}
                onChange={(e) => setBayesianPrior(Number(e.target.value))}
              />
            </label>
            <label>
              Evidence (type:strength, one per line)
              <textarea
                rows={3}
                value={bayesianEvidence}
                onChange={(e) => setBayesianEvidence(e.target.value)}
                placeholder="attestation:0.8&#10;liability:0.3"
              />
            </label>
            <button className="primary" onClick={runBayesian} disabled={bayesianBusy}>
              {bayesianBusy ? "Updating…" : "Update Bayesian PD"}
            </button>
            {bayesianError && <p className="error">{bayesianError}</p>}
                {bayesianResult && (
                  <>
                    <div className="chart-container" style={{ marginTop: "1rem" }}>
                      {bayesianChartData && (
                        <Bar
                          data={bayesianChartData}
                          options={{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                              y: { beginAtZero: true, max: 100, ticks: { color: "rgb(var(--slate-400))" }, grid: { color: "rgb(var(--slate-700))" } },
                              x: { ticks: { color: "rgb(var(--slate-400))" }, grid: { display: false } },
                            },
                          }}
                        />
                      )}
                    </div>
                    <MetricGrid
                      items={[
                        ["Prior PD", `${((bayesianResult.inputs as Record<string, number>).prior_pd * 100).toFixed(2)}%`],
                        ["Posterior PD", `${(bayesianResult.outputs.posterior_pd * 100).toFixed(2)}%`],
                        ["Posterior Alpha", String(bayesianResult.outputs.posterior_alpha)],
                        ["Posterior Beta", String(bayesianResult.outputs.posterior_beta)],
                        ["95% CI Lower", `${((bayesianResult.outputs.confidence_interval_95 as { lower: number }).lower * 100).toFixed(2)}%`],
                        ["95% CI Upper", `${((bayesianResult.outputs.confidence_interval_95 as { upper: number }).upper * 100).toFixed(2)}%`],
                      ]}
                    />
                  </>
                )}
          </section>

          <section className="card animate-fade-in">
            <h2>Risk Assessment</h2>
            <MetricGrid
              items={[
                ["Credit Score", String(assessment.credit_score)],
                ["PD", `${(assessment.probability_of_default * 100).toFixed(2)}%`],
                ["Expected Loss", `${assessment.expected_loss.toFixed(2)} CTC`],
                ["Required Collateral", `${(assessment.required_collateral_ratio * 100).toFixed(0)}%`],
                ["Stress LTV", `${(assessment.stress_ltv * 100).toFixed(0)}%`],
                ["Regime", assessment.market_regime],
              ]}
            />
            <h3>Principal Risk Factors</h3>
            <ul>
              {assessment.principal_risk_factors.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </section>

          <section className="card animate-fade-in">
            <h2>Credit Recommendation</h2>
            <p className="decision-chip" data-status={decision.decision_status}>
              {decision.decision_status} · {decision.approval_status}
            </p>
            <MetricGrid
              items={[
                ["Recommended", `${decision.recommended_amount} CTC`],
                ["Requested", `${decision.requested_amount} CTC`],
                ["Collateral Value", `${decision.collateral_value} CTC`],
                ["Expected Loss", `${decision.expected_loss.toFixed(2)} CTC`],
                ["Stress Result", `${decision.stress_result.toFixed(2)}`],
                ["Decision ID", decision.decision_id],
              ]}
            />
            <h3>Supporting Evidence</h3>
            <ul>
              {decision.supporting_evidence.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
            <h3>Attestation References</h3>
            <ul>
              {decision.attestation_references.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
            <h3>Model Versions</h3>
            <p className="muted mono">{decision.model_versions.join(", ")}</p>
          </section>

          <section className="card animate-fade-in">
            <h2>Creditcoin Execution (E10)</h2>
            <label>
              Recipient (SS58 / EVM)
              <input
                placeholder="5G1… or 0x…"
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={busy || !recipient || approved || executed}
              onClick={approveAndExecute}
            >
              {executed ? "✔ Finalized" : approved ? "✔ Human-approved" : "Approve & Execute"}
            </button>

            {execution && (
              <div className="exec">
                <p>
                  <strong>Status:</strong>{" "}
                  <span className="badge" data-status={execution.status}>
                    {execution.status}
                  </span>
                </p>
                <p className="mono">
                  Tx: {execution.tx_hash ?? "pending"}
                  {execution.block ? ` · Block ${execution.block}` : ""}
                </p>
                {execution.failure && (
                  <p className="error">Failure: {execution.failure}</p>
                )}
                {executed && <p className="success">Finalized on Creditcoin ✓</p>}
              </div>
            )}

            {monitoring && (
              <div className="exec">
                <p className="muted">
                  <strong>Monitor:</strong> {monitorStatus}
                  {monitorStatus !== "finalized" && monitorStatus !== "failed" && monitorStatus !== "timeout" && (
                    <span className="muted"> (polling every 5s)</span>
                  )}
                </p>
              </div>
            )}
          </section>

          <section className="card animate-fade-in">
            <h2>Decision Override (E8-US2)</h2>
            <p className="muted">Override the recommendation with a documented reason.</p>
            <label>
              Reason
              <textarea
                rows={2}
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Risk manager adjusted exposure limit"
              />
            </label>
            <label>
              Overridden By
              <input
                type="text"
                value={overrideBy}
                onChange={(e) => setOverrideBy(e.target.value)}
              />
            </label>
            <button className="primary" onClick={overrideDecisionHandler} disabled={overrideBusy || !overrideReason.trim() || !decision}>
              {overrideBusy ? "Overriding…" : "Override Decision"}
            </button>
            {overrideError && <p className="error">{overrideError}</p>}
            {overrideResult && (
              <p className="success">Decision overridden. Status: {(overrideResult as { decision_status?: string }).decision_status ?? "overridden"}</p>
            )}
          </section>

          <section className="card animate-fade-in">
            <h2>Decision Explanation & Provenance (E9)</h2>
            <button className="primary" onClick={reconstructDecision} disabled={reconstructBusy || !decision}>
              {reconstructBusy ? "Loading…" : "Reconstruct Decision"}
            </button>
            {reconstructError && <p className="error">{reconstructError}</p>}
            {reconstruct && reconstruct.found && (
              <div className="stack">
                <MetricGrid
                  items={[
                    ["Decision ID", reconstruct.decision_id],
                    ["Status", reconstruct.decision.decision_status],
                    ["Approval", reconstruct.decision.approval_status],
                    ["Created", reconstruct.timestamp ?? ""],
                    ["Override Reason", reconstruct.decision.override_reason ?? "none"],
                    ["Overridden By", reconstruct.decision.overridden_by ?? "none"],
                  ]}
                />
                <h3>Model Parameters</h3>
                {Object.entries(reconstruct.model_parameters).map(([modelId, params]) => (
                  <details key={modelId} style={{ marginTop: 8 }}>
                    <summary>{modelId}</summary>
                    <pre className="pre">{JSON.stringify(params, null, 2)}</pre>
                  </details>
                ))}
                <h3>Risk Outputs</h3>
                <MetricGrid
                  items={[
                    ["Credit Score", String(reconstruct.risk_outputs.credit_score)],
                    ["PD", `${(reconstruct.risk_outputs.probability_of_default * 100).toFixed(2)}%`],
                    ["Expected Loss", `${reconstruct.risk_outputs.expected_loss.toFixed(2)}`],
                    ["Recommended Amount", `${reconstruct.risk_outputs.recommended_amount}`],
                  ]}
                />
                <h3>Graph Context</h3>
                <p className="muted">Market Regime: {reconstruct.graph_context.market_regime ?? "unknown"}</p>
                <p className="muted">Wallets: {reconstruct.graph_context.wallet_addresses.join(", ") || "none"}</p>
                <details style={{ marginTop: 12 }}>
                  <summary>Full Reconstruction</summary>
                  <pre className="pre">{JSON.stringify(reconstruct, null, 2)}</pre>
                </details>
              </div>
            )}
          </section>
        </>
      )}

      {error && <p className="error">{error}</p>}
      {notice && <p className="success">{notice}</p>}
    </div>
  );
}
