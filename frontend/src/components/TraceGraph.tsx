import React, { useMemo } from "react";
import clsx from "clsx";

export type TraceNodeKind =
  | "book" | "chapter" | "section" | "concept" | "formula" | "strategy"
  | "tool" | "output" | "ok" | "err" | "draft";

export interface TraceNode {
  id: string;
  label: string;
  kind: TraceNodeKind;
  detail?: string;
}

export interface TraceEdge {
  from: string;
  to: string;
  label?: string;
}

export interface TraceGraphProps {
  nodes: TraceNode[];
  edges?: TraceEdge[];
  title?: string;
  className?: string;
}

const KIND_STYLE: Record<TraceNodeKind, { fill: string; stroke: string; text: string }> = {
  book:     { fill: "#f59e0b22", stroke: "#f59e0b", text: "#fbbf24" },
  chapter:  { fill: "#6366f122", stroke: "#6366f1", text: "#a5b4fc" },
  section:  { fill: "#47556922", stroke: "#64748b", text: "#cbd5e1" },
  concept:  { fill: "#a855f722", stroke: "#a855f7", text: "#d8b4fe" },
  formula:  { fill: "#10b98122", stroke: "#10b981", text: "#6ee7b7" },
  strategy: { fill: "#0ea5e922", stroke: "#0ea5e9", text: "#7dd3fc" },
  tool:     { fill: "#06b6d422", stroke: "#06b6d4", text: "#67e8f9" },
  output:   { fill: "#f9731622", stroke: "#f97316", text: "#fdba74" },
  ok:       { fill: "#22c55e22", stroke: "#22c55e", text: "#86efac" },
  err:      { fill: "#ef444422", stroke: "#ef4444", text: "#fca5a5" },
  draft:    { fill: "#eab30822", stroke: "#eab308", text: "#fde047" },
};

const RANK_COLORS = ["#f59e0b", "#6366f1", "#a855f7", "#10b981", "#0ea5e9", "#06b6d4"];

function rankOf(kind: TraceNodeKind): number {
  const order: TraceNodeKind[] = ["book", "chapter", "section", "concept", "strategy", "formula", "tool", "output", "draft", "ok", "err"];
  return order.indexOf(kind);
}

function layout(nodes: TraceNode[], edges: TraceEdge[]) {
  const groups = new Map<number, TraceNode[]>();
  for (const n of nodes) {
    const r = rankOf(n.kind);
    const arr = groups.get(r) ?? [];
    arr.push(n);
    groups.set(r, arr);
  }
  const ranks = Array.from(groups.keys()).sort((a, b) => a - b);
  const nodePos: Record<string, { x: number; y: number }> = {};
  const edgesOut: TraceEdge[] = edges.filter((e) => nodes.some((n) => n.id === e.from) && nodes.some((n) => n.id === e.to));
  const W = 360, H = Math.max(120, ranks.length * 84);
  const xPad = 24, yPad = 40;
  ranks.forEach((r, ri) => {
    const arr = groups.get(r)!;
    const nCols = Math.min(arr.length, 4);
    const nRows = Math.ceil(arr.length / nCols);
    arr.forEach((n, i) => {
      const col = i % nCols;
      const row = Math.floor(i / nCols);
      nodePos[n.id] = {
        x: xPad + (col + 0.5) * ((W - 2 * xPad) / nCols),
        y: yPad + ri * 84 + row * 30,
      };
    });
  });
  return { nodePos, edgesOut, width: W, height: Math.max(H, ...ranks.map((_, ri) => yPad + ri * 84 + 40)) };
}

function NodeShape({ x, y, label, kind }: { x: number; y: number; label: string; kind: TraceNodeKind }) {
  const s = KIND_STYLE[kind];
  const w = Math.min(150, Math.max(70, label.length * 6.2 + 16));
  const h = 26;
  return (
    <g transform={`translate(${x - w / 2}, ${y - h / 2})`}>
      <rect x={0} y={0} width={w} height={h} rx={8} fill={s.fill} stroke={s.stroke} strokeWidth={1.2} />
      <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize={10} fill={s.text} fontFamily="monospace">
        {label.length > 26 ? `${label.slice(0, 25)}…` : label}
      </text>
      <title>{label}</title>
    </g>
  );
}

function EdgeCurve({ x1, y1, x2, y2, label }: { x1: number; y1: number; x2: number; y2: number; label?: string }) {
  const mx = (x1 + x2) / 2;
  const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  return (
    <>
      <path d={d} fill="none" stroke={RANK_COLORS[Math.round(Math.abs(y1)) % RANK_COLORS.length]} strokeWidth={1} opacity={0.65} />
      {label && <text x={mx} y={(y1 + y2) / 2 - 4} textAnchor="middle" fontSize={8} fill="#94a3b8" fontFamily="monospace">{label}</text>}
    </>
  );
}

export default function TraceGraph({ nodes, edges = [], title, className }: TraceGraphProps) {
  const uniq = useMemo(() => {
    const seen = new Set<string>();
    return nodes.filter((n) => (seen.has(n.id) ? false : (seen.add(n.id), true)));
  }, [nodes]);
  const { nodePos, edgesOut, width, height } = useMemo(() => layout(uniq, edges), [uniq, edges]);
  const kinds = Array.from(new Set(uniq.map((n) => n.kind)));
  return (
    <div className={clsx("rounded-lg border border-slate-700/70 bg-slate-950/60 p-2", className)}>
      {title && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">{title}</span>
          <span className="text-[9px] font-mono text-slate-600">· {uniq.length} nodes · {edgesOut.length} edges</span>
        </div>
      )}
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img" style={{ maxHeight: 240 }}>
        {edgesOut.map((e, i) => {
          const a = nodePos[e.from], b = nodePos[e.to];
          if (!a || !b) return null;
          return <EdgeCurve key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} label={e.label} />;
        })}
        {uniq.map((n) => {
          const p = nodePos[n.id];
          if (!p) return null;
          return <g key={n.id}><NodeShape x={p.x} y={p.y} label={n.label} kind={n.kind} />
            {n.detail && <title>{`${n.label}\n${n.detail}`}</title>}
          </g>;
        })}
      </svg>
      <div className="flex flex-wrap gap-1 mt-1.5">
        {kinds.map((k) => {
          const s = KIND_STYLE[k];
          return (
            <span key={k} className="flex items-center gap-0.5 text-[8px] font-mono text-slate-400">
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: s.stroke }} />
              {k}
            </span>
          );
        })}
      </div>
    </div>
  );
}
