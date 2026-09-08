import { useEffect, useState } from "react";
import { api } from "../../lib/creditApi";
import type { Evidence } from "../../types/credit";

export default function EvidenceTab({ borrowerId }: { borrowerId?: string }) {
  const [txHash, setTxHash] = useState("");
  const [chainKey, setChainKey] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<Evidence | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const [history, setHistory] = useState<Evidence[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  async function loadHistory() {
    setLoadingHistory(true);
    try {
      const data = await api.listEvidence(borrowerId);
      setHistory(data);
    } catch {
      // ignore history load errors
    } finally {
      setLoadingHistory(false);
    }
  }

  useEffect(() => {
    loadHistory();
  }, [borrowerId]);

  async function verify() {
    if (!txHash.trim()) return;
    setVerifying(true);
    setVerifyError(null);
    setVerifyResult(null);
    try {
      const result = await api.verifyEvidence(
        txHash.trim(),
        chainKey ? Number(chainKey) : undefined,
        borrowerId,
      );
      setVerifyResult(result);
      loadHistory();
    } catch (e) {
      setVerifyError(e instanceof Error ? e.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <h2>Attestcoin Evidence Verification</h2>
        <p className="muted">
          Verify a cross-chain transaction via Attestcoin. Provide a source-chain
          transaction hash (e.g. Ethereum Sepolia).
        </p>
        <label>
          Transaction Hash
          <input
            value={txHash}
            onChange={(e) => setTxHash(e.target.value)}
            placeholder="0x..."
          />
        </label>
        <label>
          Chain Key (optional)
          <input
            type="number"
            value={chainKey}
            onChange={(e) => setChainKey(e.target.value)}
            placeholder="Auto-resolve"
          />
        </label>
        {borrowerId && (
          <p className="muted">
            Evidence will be linked to borrower: <span className="mono">{borrowerId}</span>
          </p>
        )}
        <button className="primary" onClick={verify} disabled={verifying || !txHash.trim()}>
          {verifying ? "Verifying…" : "Verify Evidence"}
        </button>

        {verifyError && <p className="error">{verifyError}</p>}

        {verifyResult && (
          <div className="evidence-result">
            <h3>Verification Result</h3>
            <div className="metric-grid">
              <div className="metric">
                <span className="metric-label">Status</span>
                <span className={`badge data-status=${verifyResult.status}`}>{verifyResult.status}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Source Chain</span>
                <span className="metric-value">{verifyResult.source_chain}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Header</span>
                <span className="metric-value">{verifyResult.header_number ?? "—"}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Verifier</span>
                <span className="metric-value">{verifyResult.verifier ?? "—"}</span>
              </div>
              <div className="metric">
                <span className="metric-label">Verified At</span>
                <span className="metric-value">{verifyResult.verified_at ?? "—"}</span>
              </div>
            </div>
            {verifyResult.reason && (
              <p className="muted">Reason: {verifyResult.reason}</p>
            )}
            {Object.keys(verifyResult.proof).length > 0 && (
              <details>
                <summary>Proof Payload</summary>
                <pre className="pre">{JSON.stringify(verifyResult.proof, null, 2)}</pre>
              </details>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h3>Evidence History {borrowerId ? `(${borrowerId})` : ""}</h3>
        {loadingHistory && <p className="muted">Loading…</p>}
        {!loadingHistory && history.length === 0 && (
          <p className="muted">No evidence records found.</p>
        )}
        {history.length > 0 && (
          <div className="evidence-list">
            {history.map((ev) => (
              <div key={ev.evidence_id} className="evidence-row">
                <div>
                  <strong>{ev.evidence_id}</strong>
                  <span className={`badge data-status=${ev.status}`}>{ev.status}</span>
                </div>
                <div className="mono">{ev.tx_id}</div>
                <div className="muted">
                  {ev.source_chain} · {ev.verified_at ?? "unverified"}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
