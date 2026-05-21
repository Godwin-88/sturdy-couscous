import { useEffect, useRef, useState, useCallback } from "react";
import Sigma from "sigma";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { agentApi, GraphNode, GraphEdge } from "@/lib/api";
import { LABEL_COLOR } from "@/lib/utils";
import { RefreshCw, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import clsx from "clsx";

const NODE_TYPES = ["Concept", "Strategy", "Regime", "Formula", "Ticker", "Category", "QuizQuestion"];

const NODE_SIZE: Record<string, number> = {
  Strategy: 14, Regime: 12, Ticker: 11, Concept: 8, Formula: 7, Category: 9, QuizQuestion: 6,
};

export default function GraphCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef     = useRef<Sigma | null>(null);
  const graphRef     = useRef<Graph | null>(null);

  const [nodeType,  setNodeType]  = useState<string>("Concept");
  const [loading,   setLoading]   = useState(false);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [selected,  setSelected]  = useState<GraphNode["properties"] | null>(null);

  const buildGraph = useCallback(async (type: string) => {
    if (!containerRef.current) return;
    setLoading(true);
    setSelected(null);

    try {
      const [nodes, edges]: [GraphNode[], GraphEdge[]] = await Promise.all([
        agentApi.graphNodes(type, 400),
        agentApi.graphEdges(1000),
      ]);

      const g = new Graph({ multi: false, type: "directed" });

      // Index by internal id
      const idSet = new Set<number>();
      nodes.forEach(n => {
        if (!g.hasNode(String(n.id))) {
          idSet.add(n.id);
          const label = String(
            n.properties.name ?? n.properties.id ?? n.properties.formula_id ?? n.id
          );
          g.addNode(String(n.id), {
            label,
            size:  NODE_SIZE[n.labels[0]] ?? 7,
            color: LABEL_COLOR[n.labels[0]] ?? "#94a3b8",
            x: Math.random() * 10,
            y: Math.random() * 10,
            // Store for tooltip
            _labels: n.labels,
            _props:  n.properties,
          });
        }
      });

      edges.forEach(e => {
        const src = String(e.source);
        const tgt = String(e.target);
        if (g.hasNode(src) && g.hasNode(tgt) && !g.hasEdge(src, tgt)) {
          g.addEdge(src, tgt, {
            label:     e.rel_type,
            size:      1,
            color:     "#334155",
            type:      "arrow",
          });
        }
      });

      // Layout
      if (g.order > 0) {
        forceAtlas2.assign(g, {
          iterations: 150,
          settings: forceAtlas2.inferSettings(g),
        });
      }

      // Destroy previous instance
      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }

      const sigma = new Sigma(g, containerRef.current, {
        renderEdgeLabels:      false,
        defaultEdgeType:       "arrow",
        defaultNodeColor:      "#94a3b8",
        labelColor:            { color: "#cbd5e1" },
        labelSize:             11,
        labelWeight:           "normal",
        minCameraRatio:        0.05,
        maxCameraRatio:        10,
      });

      // Click node → show details
      sigma.on("clickNode", ({ node }) => {
        const attrs = g.getNodeAttributes(node);
        setSelected({ name: attrs.label, labels: attrs._labels, ...attrs._props as object });
      });

      sigma.on("clickStage", () => setSelected(null));

      sigmaRef.current = sigma;
      graphRef.current = g;
      setNodeCount(g.order);
      setEdgeCount(g.size);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    buildGraph(nodeType);
    return () => { sigmaRef.current?.kill(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeType]);

  const zoomIn  = () => sigmaRef.current?.getCamera().animatedZoom({ duration: 300 });
  const zoomOut = () => sigmaRef.current?.getCamera().animatedUnzoom({ duration: 300 });
  const reset   = () => sigmaRef.current?.getCamera().animatedReset({ duration: 300 });

  return (
    <div className="flex flex-col h-full rounded-xl border border-slate-700 overflow-hidden bg-slate-950">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-900 border-b border-slate-700 shrink-0 flex-wrap">
        {NODE_TYPES.map(t => (
          <button
            key={t}
            onClick={() => setNodeType(t)}
            className={clsx(
              "px-2 py-0.5 rounded text-xs font-mono transition-colors",
              nodeType === t
                ? "text-white border"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            )}
            style={nodeType === t ? { borderColor: LABEL_COLOR[t], color: LABEL_COLOR[t] } : {}}
          >
            {t}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-1">
          <button onClick={zoomIn}  title="Zoom in"  className="p-1 text-slate-400 hover:text-slate-200 rounded hover:bg-slate-700">
            <ZoomIn size={14} />
          </button>
          <button onClick={zoomOut} title="Zoom out" className="p-1 text-slate-400 hover:text-slate-200 rounded hover:bg-slate-700">
            <ZoomOut size={14} />
          </button>
          <button onClick={reset}   title="Reset"    className="p-1 text-slate-400 hover:text-slate-200 rounded hover:bg-slate-700">
            <Maximize2 size={14} />
          </button>
          <button
            onClick={() => buildGraph(nodeType)}
            title="Refresh"
            className="p-1 text-slate-400 hover:text-indigo-400 rounded hover:bg-slate-700"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex gap-4 px-3 py-1 bg-slate-900/50 border-b border-slate-800 text-xs font-mono text-slate-500 shrink-0">
        <span>{nodeCount} nodes</span>
        <span>{edgeCount} edges</span>
        {loading && <span className="text-indigo-400 animate-pulse">Loading...</span>}
      </div>

      {/* Canvas + sidebar */}
      <div className="flex flex-1 min-h-0">
        <div ref={containerRef} className="flex-1 min-h-0" />

        {/* Node detail panel */}
        {selected && (
          <div className="w-64 border-l border-slate-700 bg-slate-900 p-3 overflow-y-auto text-xs font-mono shrink-0">
            <div className="text-slate-400 uppercase tracking-wider mb-2 text-[10px]">
              {(selected.labels as string[] | undefined)?.join(" · ") ?? "Node"}
            </div>
            <div className="text-slate-100 font-bold text-sm mb-3 break-words">
              {String(selected.name ?? "")}
            </div>
            <div className="space-y-1.5">
              {Object.entries(selected)
                .filter(([k]) => !["name", "labels", "_labels", "_props"].includes(k))
                .map(([k, v]) => (
                  <div key={k}>
                    <div className="text-slate-500 text-[10px] uppercase">{k}</div>
                    <div className="text-slate-300 break-words">{String(v)}</div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
