import { useEffect, useState } from "react";
import { settingsApi, authStore, type BrokerCredListItem, type SettingsStatus } from "../lib/api";
import { RefreshCw, KeyRound, Shield, Sliders, Wallet } from "lucide-react";

const RISK_META = [
  { key: "AGENT_KELLY_FRACTION", label: "Kelly Fraction", min: 0, max: 1, step: 0.05, hint: "Fraction of half-kelly applied - 0.5 = half-kelly base" },
  { key: "AGENT_MAX_POSITION_PCT", label: "Max Position %", min: 0, max: 1, step: 0.01, hint: "Largest single position as fraction of NAV" },
  { key: "RISK_MAX_SECTOR_PCT", label: "Max Sector %", min: 0, max: 1, step: 0.01, hint: "Max exposure per sector as fraction of NAV" },
  { key: "RISK_VAR_CONFIDENCE", label: "VaR Confidence", min: 0.9, max: 0.999, step: 0.001, hint: "Confidence level for VaR (0.99 = 99%)" },
  { key: "RISK_MAX_VAR_PCT", label: "Max VaR %", min: 0, max: 0.25, step: 0.01, hint: "Max portfolio VaR as % of NAV before halt" },
  { key: "AGENT_MAX_DRAWDOWN_HALT", label: "Max Drawdown Halt", min: 0, max: 0.5, step: 0.01, hint: "Drawdown from peak that triggers the trading halt" },
] as const;

export default function SettingsPanel() {
  const [token, setToken] = useState(authStore.getToken());
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [brokers, setBrokers] = useState<BrokerCredListItem[]>([]);
  const [risk, setRisk] = useState<Record<string,string>>({});
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [tab, setTab] = useState<"account" | "brokers" | "keys" | "risk">("account");
  const [brokerForm, setBrokerForm] = useState({ broker: "alpaca", key_id: "", secret: "", nickname: "", base_url: "", paper: true });
  const [groqKey, setGroqKey] = useState(""); const [groqModel, setGroqModel] = useState("");
  const [feathKey, setFeathKey] = useState(""); const [feathModel, setFeathModel] = useState("");
  const [msg, setMsg] = useState(""); const [busy, setBusy] = useState(false);

  const refresh = async (tok?: string) => {
    const t = tok ?? authStore.getToken();
    if (t) {
      try {
        const [st, bs, rk] = await Promise.all([settingsApi.status(), settingsApi.listBrokers(), settingsApi.getRisk()]);
        setStatus(st); setBrokers(bs); setRisk(rk);
      } catch (e) { setMsg("load: " + (e instanceof Error ? e.message : "")); }
    }
  };

  useEffect(() => { if (token) refresh(token); }, [token]);

  const doAuth = async (mode: "register" | "login") => {
    setBusy(true); setMsg("");
    try {
      const r = mode === "register" ? await settingsApi.register(user, pass) : await settingsApi.login(user, pass);
      authStore.setToken(r.token); setToken(r.token); setMsg(mode + " ok as " + r.user); await refresh(r.token);
    } catch (e) { setMsg(e instanceof Error ? e.message : ""); } finally { setBusy(false); }
  };

  const logout = () => { authStore.setToken(null); setToken(null); setStatus(null); setBrokers([]); setMsg("logged out"); };

  const saveBroker = async () => {
    setBusy(true); setMsg("");
    try {
      await settingsApi.saveBroker(brokerForm);
      setBrokerForm({ broker: "open", key_id: "", secret: "", nickname: "", base_url: "", paper: true });
      await refresh(); setMsg("broker saved (masked)");
    } catch (e) { setMsg(e instanceof Error ? e.message : ""); } finally { setBusy(false); }
  };

  const setActive = async (id: number, broker: string) => { try { await settingsApi.setActive(broker, id); await refresh(); setMsg("active set"); } catch (e) { setMsg(e instanceof Error ? e.message : ""); } };
  const delBroker = async (id: number) => { try { await settingsApi.deleteBroker(id); await refresh(); setMsg("deleted"); } catch (e) { setMsg(e instanceof Error ? e.message : ""); } };

  const saveKeys = async () => {
    setBusy(true); setMsg("");
    try {
      if (groqKey) await settingsApi.saveApiKey("groq", groqKey, "https://api.groq.com/openai/v1", groqModel);
      if (feathKey) await settingsApi.saveApiKey("featherless", feathKey, "https://api.featherless.ai/v1", feathModel);
      await refresh(); setMsg("API keys saved"); setGroqKey(""); setFeathKey("");
    } catch (e) { setMsg(e instanceof Error ? e.message : ""); } finally { setBusy(false); }
  };

  const saveRisk = async () => {
    setBusy(true); setMsg("");
    try { const r = await settingsApi.putRisk(risk); setRisk(r); setMsg("risk thresholds saved (apply next cycle)"); }
    catch (e) { setMsg(e instanceof Error ? e.message : ""); } finally { setBusy(false); }
  };

  const setRiskVal = (k: string, v: string) => setRisk({ ...risk, [k]: v });
  const input = "w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200";
  const btn = "px-3 py-1.5 rounded bg-indigo-600/30 border border-indigo-500/40 text-xs text-indigo-200 hover:bg-indigo-600/50 disabled:opacity-50";
  return (
    <div className="px-4 py-3 h-full overflow-y-auto">
      <div className="flex items-center gap-2 mb-3">
        <Sliders size={16} className="text-indigo-300" />
        <span className="text-sm font-semibold text-slate-200 uppercase tracking-widest">Settings</span>
      </div>
      {msg && <div className="mb-2 text-[11px] font-mono text-amber-300 bg-amber-950/20 border border-amber-800 rounded p-2">{msg}</div>}
      {!token ? (
        <div className="max-w-md rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-2">
          <div className="flex items-center gap-2"><KeyRound size={14} className="text-indigo-300" /><span className="text-xs font-semibold text-slate-200">Sign in</span></div>
          <input className={input} placeholder="username" value={user} onChange={(e) => setUser(e.target.value)} />
          <input className={input} type="password" placeholder="passphrase (min 6)" value={pass} onChange={(e) => setPass(e.target.value)} />
          <div className="flex gap-2">
            <button className={btn} disabled={busy} onClick={() => doAuth("login")}>Login</button>
            <button className={btn} disabled={busy} onClick={() => doAuth("register")}>Register</button>
          </div>
          <p className="text-[10px] text-slate-500">One account per workstation. Passphrase hashed (scrypt); broker keys encrypted at rest.</p>
        </div>
      ) : (
        <>
          <div className="flex gap-2 mb-3 flex-wrap">
            {([["account","Account"],["brokers","Brokers"],["keys","API Keys"],["risk","Risk"]] as const).map(([id,l]) => (
              <button key={id} onClick={() => setTab(id)}
                className={`px-3 py-1.5 rounded text-xs ${tab === id ? "bg-indigo-600/40 text-indigo-100 border border-indigo-500/50" : "bg-slate-800 text-slate-300 border border-slate-700"}`}>{l}</button>
            ))}
            <button onClick={logout} className="ml-auto px-3 py-1.5 rounded text-xs bg-rose-800/30 text-rose-300 border border-rose-700">Logout</button>
          </div>

          {tab === "account" && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 text-xs text-slate-300">
              <p className="mb-1 text-slate-200"><Shield size={14} className="inline mr-1" />Signed in. Broker accounts and API keys below are scoped to you.</p>
              <p className="text-slate-500 text-[11px]">Status: brokers {status?.brokers_configured?.join(", ") || "none"} - api keys {status?.api_keys?.join(", ") || "none"} - active {Object.keys(status?.active ?? {}).join(", ") || "none"}</p>
            </div>
          )}

          {tab === "brokers" && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-2">
                <div className="flex items-center gap-2"><Wallet size={14} className="text-emerald-300" /><span className="text-xs font-semibold text-slate-200">Add broker connection</span></div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <select className={input} value={brokerForm.broker} onChange={(e) => setBrokerForm({ ...brokerForm, broker: e.target.value })}>
                    <option value="alpaca">Alpaca</option><option value="kraken">Kraken (legacy)</option>
                  </select>
                  <input className={input} placeholder="key id" value={brokerForm.key_id} onChange={(e) => setBrokerForm({ ...brokerForm, key_id: e.target.value })} />
                  <input className={input} type="password" placeholder="secret" value={brokerForm.secret} onChange={(e) => setBrokerForm({ ...brokerForm, secret: e.target.value })} />
                  <input className={input} placeholder="nickname" value={brokerForm.nickname} onChange={(e) => setBrokerForm({ ...brokerForm, nickname: e.target.value })} />
                </div>
                <div className="flex items-center gap-3 text-[11px] text-slate-400">
                  <label className="flex items-center gap-1"><input type="checkbox" checked={brokerForm.paper} onChange={(e) => setBrokerForm({ ...brokerForm, paper: e.target.checked })} /> paper</label>
                  {!brokerForm.paper && <span className="text-rose-400">LIVE - verify carefully</span>}
                  <button className={btn} disabled={busy} onClick={saveBroker}>Save (encrypted)</button>
                </div>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-3">
                <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-2">Saved connections</div>
                {brokers.length === 0 && <p className="text-xs text-slate-500">None yet.</p>}
                {brokers.map((b) => (
                  <div key={b.id} className="flex items-center gap-3 py-1.5 border-b border-slate-800 last:border-0 text-xs">
                    <span className="text-slate-300 w-20">{b.broker}</span>
                    <span className="text-slate-400 font-mono">{b.key_id ?? ""}</span>
                    {b.is_active && <span className="text-[10px] bg-emerald-900/40 border border-emerald-700 px-1.5 rounded text-emerald-300">ACTIVE</span>}
                    <span className={`text-[10px] ${b.paper ? "text-slate-500" : "text-rose-400"}`}>{b.paper ? "paper" : "LIVE"}</span>
                    <div className="ml-auto flex gap-2">
                      {!b.is_active && <button className="text-[10px] text-indigo-300 hover:underline" onClick={() => setActive(b.id, b.broker)}>Set active</button>}
                      <button className="text-[10px] text-rose-400 hover:underline" onClick={() => delBroker(b.id)}>Delete</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {tab === "keys" && (
            <div className="space-y-3">
              <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-2">
                <div className="text-xs font-semibold text-slate-200">Groq (primary)</div>
                <input className={input} type="password" placeholder="Groq API key (masked after save)" value={groqKey} onChange={(e) => setGroqKey(e.target.value)} />
                <input className={input} placeholder="model" value={groqModel} onChange={(e) => setGroqModel(e.target.value)} />
                <div className="text-xs font-semibold text-slate-200 pt-1">Featherless (fallback)</div>
                <input className={input} type="password" placeholder="Featherless API key" value={feathKey} onChange={(e) => setFeathKey(e.target.value)} />
                <input className={input} placeholder="model" value={feathModel} onChange={(e) => setFeathModel(e.target.value)} />
                <button className={btn} disabled={busy} onClick={saveKeys}>Save keys</button>
                <p className="text-[10px] text-slate-500">Configured: {status?.api_keys?.join(", ") || "none"}. Keys encrypted at rest; engine reads them next cycle.</p>
              </div>
            </div>
          )}

          {tab === "risk" && (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-4 space-y-3">
              <div className="flex items-center gap-2"><Sliders size={14} className="text-amber-300" /><span className="text-xs font-semibold text-slate-200">Risk-engine thresholds (apply next agent cycle)</span></div>
              {RISK_META.map((r) => (
                <div key={r.key} className="grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-2 items-center">
                  <div title={r.hint}>
                    <div className="text-xs text-slate-300">{r.label}</div>
                    <div className="text-[10px] text-slate-600 font-mono">{r.key}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <input type="range" min={String(r.min)} max={String(r.max)} step={String(r.step)} value={parseFloat(risk[r.key] ?? "") || 0}
                      onChange={(e) => setRiskVal(r.key, e.target.value)} className="flex-1" />
                    <input className={input + " !w-20 text-right"} value={risk[r.key] ?? ""} onChange={(e) => setRiskVal(r.key, e.target.value)} />
                  </div>
                </div>
              ))}
              <button className={btn} disabled={busy} onClick={saveRisk}>Save thresholds</button>
              <button className={btn + " ml-2"} onClick={() => refresh()}><RefreshCw size={12} className="inline mr-1" />Reload</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
