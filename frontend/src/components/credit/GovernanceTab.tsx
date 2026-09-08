import { useEffect, useState } from "react";
import { api } from "../../lib/creditApi";
import type { AuditLogEntry, GovernanceModel, PolicyUpdateResponse } from "../../types/credit";
import MetricGrid from "./MetricGrid";

type GovSection = "register" | "policy" | "models" | "audit";

const SECTIONS: { id: GovSection; label: string }[] = [
  { id: "register", label: "Register Model" },
  { id: "policy", label: "Update Policy" },
  { id: "models", label: "Models" },
  { id: "audit", label: "Audit Log" },
];

export default function GovernanceTab() {
  const [section, setSection] = useState<GovSection>("register");

  const [models, setModels] = useState<GovernanceModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  const [regModelId, setRegModelId] = useState("");
  const [regName, setRegName] = useState("");
  const [regVersion, setRegVersion] = useState("");
  const [regOwner, setRegOwner] = useState("");
  const [regDescription, setRegDescription] = useState("");
  const [regParameters, setRegParameters] = useState("{}");
  const [regStatus, setRegStatus] = useState("active");
  const [regResult, setRegResult] = useState<GovernanceModel | null>(null);
  const [regError, setRegError] = useState<string | null>(null);
  const [regBusy, setRegBusy] = useState(false);

  const [policyId, setPolicyId] = useState("");
  const [prevValue, setPrevValue] = useState("");
  const [newValue, setNewValue] = useState("");
  const [policyUser, setPolicyUser] = useState("");
  const [policyReason, setPolicyReason] = useState("");
  const [policyResult, setPolicyResult] = useState<PolicyUpdateResponse | null>(null);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [policyBusy, setPolicyBusy] = useState(false);

  const [auditEntityType, setAuditEntityType] = useState("");
  const [auditEntityId, setAuditEntityId] = useState("");
  const [auditLog, setAuditLog] = useState<AuditLogEntry[] | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditBusy, setAuditBusy] = useState(false);

  useEffect(() => {
    setLoadingModels(true);
    api.listGovernanceModels()
      .then(setModels)
      .catch(() => {})
      .finally(() => setLoadingModels(false));
  }, []);

  async function registerModel() {
    setRegBusy(true);
    setRegError(null);
    setRegResult(null);
    try {
      let parsedParams: Record<string, unknown> = {};
      try {
        parsedParams = JSON.parse(regParameters);
      } catch {
        throw new Error("Parameters must be valid JSON");
      }
      const result = await api.registerModel({
        model_id: regModelId,
        name: regName,
        version: regVersion,
        owner: regOwner,
        description: regDescription || undefined,
        parameters: parsedParams,
        status: regStatus,
      });
      setRegResult(result);
      setRegModelId("");
      setRegName("");
      setRegVersion("");
      setRegOwner("");
      setRegDescription("");
      setRegParameters("{}");
      setRegStatus("active");
      api.listGovernanceModels().then(setModels).catch(() => {});
    } catch (e) {
      setRegError(e instanceof Error ? e.message : String(e));
    } finally {
      setRegBusy(false);
    }
  }

  async function updatePolicy() {
    setPolicyBusy(true);
    setPolicyError(null);
    setPolicyResult(null);
    try {
      let parsedPrev: unknown = null;
      let parsedNew: unknown = null;
      try {
        parsedPrev = JSON.parse(prevValue);
      } catch {
        parsedPrev = prevValue;
      }
      try {
        parsedNew = JSON.parse(newValue);
      } catch {
        parsedNew = newValue;
      }
      const result = await api.updatePolicy({
        policy_id: policyId,
        previous_value: parsedPrev,
        new_value: parsedNew,
        user: policyUser,
        reason: policyReason,
      });
      setPolicyResult(result);
      setPolicyId("");
      setPrevValue("");
      setNewValue("");
      setPolicyUser("");
      setPolicyReason("");
    } catch (e) {
      setPolicyError(e instanceof Error ? e.message : String(e));
    } finally {
      setPolicyBusy(false);
    }
  }

  async function loadAuditLog() {
    if (!auditEntityType || !auditEntityId) return;
    setAuditBusy(true);
    setAuditError(null);
    setAuditLog(null);
    try {
      const result = await api.getAuditLog(auditEntityType, auditEntityId);
      setAuditLog(result);
    } catch (e) {
      setAuditError(e instanceof Error ? e.message : String(e));
    } finally {
      setAuditBusy(false);
    }
  }

  return (
    <div className="stack">
      <nav className="tabs">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            className={`tab ${section === s.id ? "active" : ""}`}
            onClick={() => setSection(s.id)}
          >
            {s.label}
          </button>
        ))}
      </nav>

      {section === "register" && (
        <div className="stack">
          <section className="card">
            <h2>Register Model</h2>
            <p className="muted">Register a new governance model.</p>
            <label>
              Model ID
              <input type="text" value={regModelId} onChange={(e) => setRegModelId(e.target.value)} />
            </label>
            <label>
              Name
              <input type="text" value={regName} onChange={(e) => setRegName(e.target.value)} />
            </label>
            <label>
              Version
              <input type="text" value={regVersion} onChange={(e) => setRegVersion(e.target.value)} />
            </label>
            <label>
              Owner
              <input type="text" value={regOwner} onChange={(e) => setRegOwner(e.target.value)} />
            </label>
            <label>
              Description
              <input type="text" value={regDescription} onChange={(e) => setRegDescription(e.target.value)} />
            </label>
            <label>
              Parameters (JSON)
              <textarea
                rows={4}
                value={regParameters}
                onChange={(e) => setRegParameters(e.target.value)}
                placeholder='{"threshold": 0.5}'
              />
            </label>
            <label>
              Status
              <input type="text" value={regStatus} onChange={(e) => setRegStatus(e.target.value)} />
            </label>
            <button className="primary" onClick={registerModel} disabled={regBusy || !regModelId || !regName || !regVersion || !regOwner}>
              {regBusy ? "Registering…" : "Register Model"}
            </button>
          </section>

          {regError && <p className="error">{regError}</p>}

          {regResult && (
            <section className="card">
              <h3>Registered Model</h3>
              <MetricGrid
                items={[
                  ["Model ID", regResult.model_id],
                  ["Name", regResult.name],
                  ["Version", regResult.version],
                  ["Owner", regResult.owner],
                  ["Status", regResult.status],
                  ["Registered At", regResult.registered_at],
                ]}
              />
              {regResult.description && <p className="muted">{regResult.description}</p>}
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(regResult, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}

      {section === "policy" && (
        <div className="stack">
          <section className="card">
            <h2>Update Policy</h2>
            <p className="muted">Update a governance policy value.</p>
            <label>
              Policy ID
              <input type="text" value={policyId} onChange={(e) => setPolicyId(e.target.value)} />
            </label>
            <label>
              Previous Value (JSON or string)
              <input type="text" value={prevValue} onChange={(e) => setPrevValue(e.target.value)} />
            </label>
            <label>
              New Value (JSON or string)
              <input type="text" value={newValue} onChange={(e) => setNewValue(e.target.value)} />
            </label>
            <label>
              User
              <input type="text" value={policyUser} onChange={(e) => setPolicyUser(e.target.value)} />
            </label>
            <label>
              Reason
              <textarea
                rows={3}
                value={policyReason}
                onChange={(e) => setPolicyReason(e.target.value)}
              />
            </label>
            <button className="primary" onClick={updatePolicy} disabled={policyBusy || !policyId || !policyUser || !policyReason}>
              {policyBusy ? "Updating…" : "Update Policy"}
            </button>
          </section>

          {policyError && <p className="error">{policyError}</p>}

          {policyResult && (
            <section className="card">
              <h3>Policy Updated</h3>
              <MetricGrid
                items={[
                  ["Policy ID", policyResult.policy_id],
                  ["User", policyResult.user],
                  ["Effective Date", policyResult.effective_date],
                  ["Updated At", policyResult.updated_at],
                ]}
              />
              <p className="muted">Reason: {policyResult.reason}</p>
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(policyResult, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}

      {section === "models" && (
        <div className="stack">
          <section className="card">
            <h2>Registered Governance Models</h2>
            <p className="muted">Table of registered models.</p>
            {loadingModels ? (
              <p className="muted">Loading models…</p>
            ) : (
              <div className="data-status">
                <table>
                  <thead>
                    <tr>
                      <th>Model ID</th>
                      <th>Name</th>
                      <th>Version</th>
                      <th>Owner</th>
                      <th>Status</th>
                      <th>Description</th>
                      <th>Registered At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((m) => (
                      <tr key={m.model_id}>
                        <td className="mono">{m.model_id}</td>
                        <td>{m.name}</td>
                        <td>{m.version}</td>
                        <td>{m.owner}</td>
                        <td>
                          <span className="badge" data-status={m.status}>{m.status}</span>
                        </td>
                        <td className="muted">{m.description ?? "—"}</td>
                        <td className="muted">{m.registered_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      {section === "audit" && (
        <div className="stack">
          <section className="card">
            <h2>Audit Log</h2>
            <p className="muted">View audit log entries for a governance entity.</p>
            <label>
              Entity Type
              <input
                type="text"
                value={auditEntityType}
                onChange={(e) => setAuditEntityType(e.target.value)}
                placeholder="e.g. model, policy"
              />
            </label>
            <label>
              Entity ID
              <input
                type="text"
                value={auditEntityId}
                onChange={(e) => setAuditEntityId(e.target.value)}
                placeholder="e.g. model_001"
              />
            </label>
            <button className="primary" onClick={loadAuditLog} disabled={auditBusy || !auditEntityType || !auditEntityId}>
              {auditBusy ? "Loading…" : "Load Audit Log"}
            </button>
          </section>

          {auditError && <p className="error">{auditError}</p>}

          {auditLog && (
            <section className="card">
              <h3>Audit Entries</h3>
              {auditLog.length === 0 ? (
                <p className="muted">No audit entries found.</p>
              ) : (
                <div className="data-status">
                  <table>
                    <thead>
                      <tr>
                        <th>Action</th>
                        <th>Actor</th>
                        <th>Timestamp</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLog.map((entry, idx) => (
                        <tr key={`${entry.entity_type}-${entry.entity_id}-${entry.action}-${idx}`}>
                          <td>{entry.action}</td>
                          <td>{entry.actor}</td>
                          <td className="muted">{entry.timestamp}</td>
                          <td className="mono">{JSON.stringify(entry.details)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <details style={{ marginTop: 12 }}>
                <summary>Raw Model Output</summary>
                <pre className="pre">{JSON.stringify(auditLog, null, 2)}</pre>
              </details>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
