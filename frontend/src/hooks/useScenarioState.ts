import { useEffect, useState } from "react";
import { api } from "../lib/creditApi";
import type { RiskRegime } from "../types/credit";

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

const SOURCES = [
  { id: "portfolio", label: "Portfolio (real data)", desc: "Derive P&L from actual portfolio exposure + regime volatility" },
  { id: "borrower", label: "Borrower", desc: "Derive P&L from a specific borrower's state" },
  { id: "sample", label: "Sample Scenarios", desc: "Deterministic regime-aware distributions" },
  { id: "custom", label: "Custom P&L", desc: "Paste or edit your own P&L series" },
];

const SAMPLE_PRESETS: Record<string, { label: string; description: string; pnl: number[] }> = {
  bull: {
    label: "Bull Market",
    description: "Steady upward drift, low volatility",
    pnl: Array.from({ length: 20 }, () => Number((Math.random() * 60 + 10).toFixed(2))),
  },
  bear: {
    label: "Bear Market",
    description: "Persistent negative returns, elevated vol",
    pnl: Array.from({ length: 20 }, () => Number((-Math.random() * 80 - 20).toFixed(2))),
  },
  sideways: {
    label: "Sideways / Choppy",
    description: "Mean-reverting with clustered volatility",
    pnl: Array.from({ length: 20 }, () => Number((Math.random() * 160 - 80).toFixed(2))),
  },
  crisis: {
    label: "Crisis",
    description: "Fat-tail losses, high volatility",
    pnl: Array.from({ length: 20 }, () => Number((-Math.random() * 200 - 50).toFixed(2))),
  },
};

export interface ScenarioState {
  source: string;
  borrowerId: string;
  regime: RiskRegime;
  exposure: number;
  confidence: number;
  days: number;
  customPnl: string;
  pnl: number[];
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
}

export interface ScenarioActions {
  generate: () => void;
  analyze: () => void;
  applyPreset: (key: string) => void;
  setSource: (s: string) => void;
  setBorrowerId: (s: string) => void;
  setRegime: (r: RiskRegime) => void;
  setExposure: (n: number) => void;
  setConfidence: (n: number) => void;
  setDays: (n: number) => void;
  setCustomPnl: (s: string) => void;
  setPnl: (pnl: number[]) => void;
}

export interface ScenarioMeta {
  SOURCES: typeof SOURCES;
  REGIMES: typeof REGIMES;
  SAMPLE_PRESETS: typeof SAMPLE_PRESETS;
}

export function useScenarioState(initialRegime: RiskRegime = "high_volatility"): ScenarioState & ScenarioActions & ScenarioMeta {
  const [source, setSource] = useState("sample");
  const [borrowerId, setBorrowerId] = useState("");
  const [regime, setRegime] = useState<RiskRegime>(initialRegime);
  const [exposure, setExposure] = useState(1_000_000);
  const [confidence, setConfidence] = useState(0.95);
  const [days, setDays] = useState(20);
  const [customPnl, setCustomPnl] = useState(
    Array.from({ length: 20 }, () => (Math.random() * 200 - 100).toFixed(2)).join("\n")
  );
  const [pnl, setPnl] = useState<number[]>([]);
  const [generating, setGenerating] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScenarioState["result"]>(null);

  const [borrowers, setBorrowers] = useState<string[]>([]);

  useEffect(() => {
    api.listBorrowers().then(setBorrowers).catch(() => {});
  }, []);

  async function generate() {
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      let pnlData: number[];
      if (source === "custom") {
        const lines = customPnl.split(/[\n,]+/).map((s) => parseFloat(s.trim())).filter((n) => !Number.isNaN(n));
        if (lines.length < 2) throw new Error("Enter at least 2 P&L observations");
        pnlData = lines;
      } else if (source === "borrower") {
        if (!borrowerId) throw new Error("Select a borrower");
        const res = await api.generateScenario({
          source: "borrower",
          borrower_id: borrowerId,
          regime,
          exposure,
          confidence,
          days,
        });
        pnlData = res.outputs.pnl;
      } else if (source === "portfolio") {
        const res = await api.generateScenario({
          source: "portfolio",
          regime,
          exposure,
          confidence,
          days,
        });
        pnlData = res.outputs.pnl;
      } else {
        const res = await api.generateScenario({
          source: "sample",
          regime,
          exposure,
          confidence,
          days,
        });
        pnlData = res.outputs.pnl;
      }
      setPnl(pnlData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate scenario");
    } finally {
      setGenerating(false);
    }
  }

  async function analyze() {
    if (pnl.length === 0) return;
    setAnalyzing(true);
    setError(null);
    try {
      const res = await api.analyzeScenario({
        pnl,
        exposure,
        shock_pct: -0.20,
        recovery_rate: 0.4,
        pd: 0.05,
        lgd: 0.4,
        confidence,
      });
      setResult({
        var: res.outputs.var.var,
        cvar: res.outputs.cvar.cvar,
        stressLoss: res.outputs.stress.stressed_loss,
        stressedExposure: res.outputs.stress.stressed_exposure,
        expectedLoss: res.outputs.expected_loss.expected_loss,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze scenario");
    } finally {
      setAnalyzing(false);
    }
  }

  function applyPreset(presetKey: string) {
    const preset = SAMPLE_PRESETS[presetKey];
    if (!preset) return;
    setSource("custom");
    setCustomPnl(preset.pnl.join("\n"));
    setPnl(preset.pnl);
    setResult(null);
  }

  return {
    source, setSource,
    borrowerId, setBorrowerId,
    regime, setRegime,
    exposure, setExposure,
    confidence, setConfidence,
    days, setDays,
    customPnl, setCustomPnl,
    pnl, setPnl,
    generating, analyzing, error, result,
    borrowers,
    generate, analyze, applyPreset,
    SOURCES, REGIMES, SAMPLE_PRESETS,
  };
}
