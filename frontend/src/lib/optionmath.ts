// Client-side option math for the GraphAlpha Options trade desk.
// Black-Scholes pricing + P&L / greeks surface generators used by the
// pay-off and 3D surface diagrams in the Options panel.

export interface PnLLeg {
  strike: number;
  contract_type: "call" | "put";
  side: "long" | "short";
  contracts: number;
  multiplier: number;
  premium: number;      // per-share premium paid / received
  iv: number;           // implied volatility (decimal)
}

/** Standard-normal CDF (Abramowitz & Stegun 7.1.26). */
export function nd(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d =
    0.31938153 * t -
    0.356563782 * t * t +
    1.781477937 * t * t * t -
    1.821255978 * t * t * t * t +
    1.330274429 * Math.pow(t, 5);
  const phi = 0.3989422804014327 * Math.exp(-0.5 * z * z);
  return z >= 0 ? 1 - phi * d : phi * d;
}

export interface BsResult {
  call: number;
  put: number;
  delta_call: number;
  delta_put: number;
  gamma: number;
  theta_call: number;
  theta_put: number;
  vega: number;         // per 1 vol point
}

/** Black-Scholes price + greeks. T is time-to-expiry in years. */
export function bsPrice(S: number, K: number, T: number, sigma: number, r = 0.0): BsResult {
  if (T <= 0) {
    return {
      call: Math.max(S - K, 0),
      put: Math.max(K - S, 0),
      delta_call: S > K ? 1 : 0,
      delta_put: S < K ? -1 : 0,
      gamma: 0,
      theta_call: 0,
      theta_put: 0,
      vega: 0,
    };
  }
  if (sigma <= 0 || S <= 0 || K <= 0) {
    return {
      call: Math.max(S - K, 0),
      put: Math.max(K - S, 0),
      delta_call: 0, delta_put: 0, gamma: 0, theta_call: 0, theta_put: 0, vega: 0,
    };
  }
  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrtT);
  const d2 = d1 - sigma * sqrtT;
  const phi = 0.3989422804014327;
  const call = S * nd(d1) - K * Math.exp(-r * T) * nd(d2);
  const put = K * Math.exp(-r * T) * nd(-d2) - S * nd(-d1);
  const gamma = (phi * Math.exp(-0.5 * d1 * d1)) / (S * sigma * sqrtT);
  const vega = S * phi * Math.exp(-0.5 * d1 * d1) * sqrtT / 100;
  const theta_call = (-S * phi * Math.exp(-0.5 * d1 * d1) * sigma / (2 * sqrtT)
    - r * K * Math.exp(-r * T) * nd(d2)) / 365;
  const theta_put = (-S * phi * Math.exp(-0.5 * d1 * d1) * sigma / (2 * sqrtT)
    + r * K * Math.exp(-r * T) * nd(-d2)) / 365;
  return { call, put, delta_call: nd(d1), delta_put: nd(d1) - 1, gamma, theta_call, theta_put, vega };
}

/** P&L of a single leg at spot S with T years to expiry. */
export function legPnl(leg: PnLLeg, S: number, T: number, r = 0): number {
  const px = leg.contract_type === "call"
    ? bsPrice(S, leg.strike, T, leg.iv, r).call
    : bsPrice(S, leg.strike, T, leg.iv, r).put;
  const sign = leg.side === "long" ? 1 : -1;
  return sign * (px - leg.premium) * leg.contracts * leg.multiplier;
}

export function legSumPnl(legs: PnLLeg[], S: number, T: number, r = 0): number {
  return legs.reduce((acc, l) => acc + legPnl(l, S, T, r), 0);
}

export interface SurfaceResult {
  x: number[];       // columns (e.g. spot)
  y: number[];       // rows (e.g. DTE)
  values: number[][]; // [rowIdx][colIdx]
}

/** 3D P&L surface over spot x DTE for a set of legs. */
export function pnlSurface(
  legs: PnLLeg[],
  spot0: number,
  dte0: number,
  opts: { xSteps?: number; ySteps?: number; pct?: number; r?: number } = {},
): SurfaceResult {
  const { xSteps = 14, ySteps = 5, pct = 0.25, r = 0 } = opts;
  const lo = spot0 * (1 - pct);
  const hi = spot0 * (1 + pct);
  const x: number[] = [];
  for (let i = 0; i < xSteps; i++) x.push(lo + ((hi - lo) * i) / Math.max(1, xSteps - 1));
  const dte = Math.max(1, Math.round(dte0));
  const y: number[] = [];
  for (let j = 0; j < ySteps; j++) y.push((dte * j) / Math.max(1, ySteps - 1)); // 0 → dte days
  const values = y.map(t => x.map(s => legSumPnl(legs, s, t / 365, r)));
  return { x, y, values };
}

export type GreekName = "delta" | "gamma" | "theta" | "vega";

/** 3D greeks surface across strike x DTE derived from chain rows (Black-Scholes). */
export function greekSurface(
  rows: { strike: number; iv: number | null | undefined }[],
  spot0: number,
  dtes: number[],
  greek: GreekName,
  contractType: "call" | "put",
): SurfaceResult {
  const sorted = [...rows].sort((a, b) => a.strike - b.strike);
  const strikes = sorted.map(r => r.strike);
  const ives = sorted.map(r => r.iv ?? 0.2);
  const values = dtes.map(dteOnes =>
    strikes.map((K, i) => {
      const g = bsPrice(spot0, K, dteOnes / 365, ives[i]);
      switch (greek) {
        case "delta": return contractType === "call" ? g.delta_call : g.delta_put;
        case "gamma": return g.gamma;
        case "vega": return g.vega;
        case "theta": return contractType === "call" ? g.theta_call : g.theta_put;
      }
    }),
  );
  return { x: strikes, y: dtes, values };
}

/** Contract symbol parser → {root, expiry, right, strike} e.g. SPY260904C00770000. */
export function parseContractSymbol(sym: string): { root: string; expiry: string; right: "C" | "P"; strike: number } | null {
  const m = sym.match(/^([A-Z]{1,5})(\d{6})([CP])(\d{8})$/);
  if (!m) return null;
  const [, root, yymmdd, right, strikeStr] = m;
  const strike = Number(strikeStr) / 1000;
  const expiry = `20${yymmdd.slice(0, 2)}-${yymmdd.slice(2, 4)}-${yymmdd.slice(4, 6)}`;
  return { root, expiry, right: right as "C" | "P", strike };
}