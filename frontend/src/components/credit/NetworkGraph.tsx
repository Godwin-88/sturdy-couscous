import { useEffect, useRef, useState } from "react";

interface Node {
  id: string;
  label: string;
  group: string;
}

interface Edge {
  source: string;
  target: string;
  label: string;
}

interface NetworkGraphProps {
  entities: { name: string; type?: string }[];
  relationships: string[];
  paths: string[];
}

function parseRelationships(rels: string[]): Edge[] {
  return rels
    .map((r) => {
      const parts = r.split(/\s*[-–—]\s*/);
      if (parts.length >= 3) {
        return { source: parts[0], target: parts[2], label: parts[1] };
      }
      return null;
    })
    .filter((e): e is Edge => e !== null);
}

function parsePaths(paths: string[]): Edge[] {
  return paths.flatMap((p) => {
    const parts = p.split(/\s*→\s*/).filter(Boolean);
    const edges: Edge[] = [];
    for (let i = 0; i < parts.length - 1; i++) {
      edges.push({ source: parts[i], target: parts[i + 1], label: "→" });
    }
    return edges;
  });
}

const COLORS = [
  "#3fb950", "#6a84de", "#4a63c8", "#f85149", "#7d89b8",
  "#4a63c8", "#8fa6ec", "#6a84de",
];

export default function NetworkGraph({ entities, relationships, paths }: NetworkGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 600, height: 400 });

  const nodes: Node[] = entities.map((e) => ({
    id: e.name,
    label: e.name,
    group: e.type || "inferred",
  }));

  const edges = [...parseRelationships(relationships), ...parsePaths(paths)];
  const uniqueNodes = Array.from(
    new Map(
      edges.flatMap((e) => [
        [e.source, { id: e.source, label: e.source, group: "inferred" }],
        [e.target, { id: e.target, label: e.target, group: "inferred" }],
      ])
    ).values()
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setSize({ width: Math.max(width, 300), height: Math.max(height, 250) });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size.width * dpr;
    canvas.height = size.height * dpr;
    ctx.scale(dpr, dpr);

    ctx.fillStyle = "#030214";
    ctx.fillRect(0, 0, size.width, size.height);

    const allNodes = uniqueNodes.length > 0 ? uniqueNodes : nodes;
    const centerX = size.width / 2;
    const centerY = size.height / 2;
    const radius = Math.min(size.width, size.height) * 0.35;

    const positions = new Map<string, { x: number; y: number }>();
    allNodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / allNodes.length - Math.PI / 2;
      positions.set(node.id, {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      });
    });

    ctx.strokeStyle = "#182250";
    ctx.lineWidth = 1;
    edges.forEach((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (source && target) {
        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);
        ctx.stroke();

        const midX = (source.x + target.x) / 2;
        const midY = (source.y + target.y) / 2;
        ctx.fillStyle = "#525f8e";
        ctx.font = "10px Raleway";
        ctx.textAlign = "center";
        ctx.fillText(edge.label, midX, midY - 4);
      }
    });

    allNodes.forEach((node, i) => {
      const pos = positions.get(node.id);
      if (!pos) return;
      const color = COLORS[i % COLORS.length];

      ctx.beginPath();
      ctx.arc(pos.x, pos.y, 18, 0, 2 * Math.PI);
      ctx.fillStyle = "#0c143a";
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = color;
      ctx.font = "bold 10px Raleway";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(node.label.slice(0, 8), pos.x, pos.y);

      ctx.fillStyle = "#e8ebf7";
      ctx.font = "11px Raleway";
      ctx.fillText(node.label, pos.x, pos.y + 30);
    });
  }, [uniqueNodes, edges, size, nodes]);

  if (uniqueNodes.length === 0 && nodes.length === 0) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
        Run a query to visualize the knowledge graph
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: "100%", height: "400px", marginTop: "1rem", borderRadius: "12px", overflow: "hidden", border: "1px solid var(--border)" }}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "100%", display: "block" }}
        aria-label="Knowledge graph visualization"
        role="img"
      />
    </div>
  );
}
