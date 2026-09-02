import { useState, useMemo } from "react";
import { RotateCcw } from "lucide-react";

interface GreekGreeks {
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

interface Greeks3DVisualizationProps {
  greeks: GreekGreeks;
  title?: string;
  size?: number;
}

export default function Greeks3DVisualization({ greeks, title = "Portfolio Greeks", size = 200 }: Greeks3DVisualizationProps) {
  const [rotation, setRotation] = useState({ x: -25, y: 35 });
  const [isDragging, setIsDragging] = useState(false);
  const [lastPos, setLastPos] = useState({ x: 0, y: 0 });

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setLastPos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - lastPos.x;
    const dy = e.clientY - lastPos.y;
    setRotation(prev => ({
      x: Math.max(-90, Math.min(90, prev.x - dy * 0.5)),
      y: prev.y + dx * 0.5,
    }));
    setLastPos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseUp = () => setIsDragging(false);

  const resetView = () => setRotation({ x: -25, y: 35 });

  const bars = useMemo(() => {
    const maxVal = Math.max(Math.abs(greeks.delta), Math.abs(greeks.gamma) * 10, Math.abs(greeks.theta) / 10, Math.abs(greeks.vega), 1);
    return [
      { label: "Δ", value: greeks.delta, color: "#10b981", max: maxVal },
      { label: "Γ", value: greeks.gamma * 10, color: "#6366f1", max: maxVal },
      { label: "Θ", value: greeks.theta / 10, color: "#f59e0b", max: maxVal },
      { label: "V", value: greeks.vega, color: "#ec4899", max: maxVal },
    ];
  }, [greeks]);

  const barWidth = 30;
  const barSpacing = 50;
  const baseZ = -20;
  const scale = (size * 0.3);

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-950">
        <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">{title}</span>
        <div className="flex items-center gap-1">
          <button onClick={resetView} className="p-1 rounded text-slate-500 hover:text-slate-300" title="Reset view">
            <RotateCcw size={12} />
          </button>
          <span className="text-[10px] font-mono text-slate-500">drag to rotate</span>
        </div>
      </div>
      <div
        className="relative cursor-grab active:cursor-grabbing overflow-hidden"
        style={{ height: size + 60, perspective: "800px" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: "preserve-3d" }}
        >
          <div
            style={{
              transformStyle: "preserve-3d",
              transform: `rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)`,
              width: size,
              height: size,
              position: "relative",
            }}
          >
            {/* Base grid */}
            <div
              className="absolute border border-slate-700/50"
              style={{
                width: size * 0.8,
                height: size * 0.8,
                left: "10%",
                top: "10%",
                transform: `translateZ(${baseZ}px)`,
                transformStyle: "preserve-3d",
                background: "linear-gradient(rgba(100,116,139,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(100,116,139,0.1) 1px, transparent 1px)",
                backgroundSize: "20px 20px",
              }}
            />

            {/* 3D Bars */}
            {bars.map((bar, i) => {
              const height = (Math.abs(bar.value) / bar.max) * scale;
              const xOffset = (i - 1.5) * barSpacing;
              const isNegative = bar.value < 0;

              return (
                <div
                  key={bar.label}
                  className="absolute"
                  style={{
                    left: `calc(50% + ${xOffset}px - ${barWidth / 2}px)`,
                    top: "50%",
                    width: barWidth,
                    height: height,
                    transformStyle: "preserve-3d",
                    transform: `translateZ(${baseZ + 1}px)`,
                  }}
                >
                  {/* Bar front face */}
                  <div
                    className="absolute w-full transition-all duration-300"
                    style={{
                      height: height,
                      bottom: isNegative ? "0" : "auto",
                      top: isNegative ? "auto" : "0",
                      background: `linear-gradient(${isNegative ? "0deg" : "180deg"}, ${bar.color}dd, ${bar.color}88)`,
                      border: `1px solid ${bar.color}`,
                      borderRadius: "2px",
                      boxShadow: `0 0 15px ${bar.color}44`,
                    }}
                  />
                  {/* Bar top face (3D effect) */}
                  <div
                    className="absolute w-full"
                    style={{
                      height: "8px",
                      top: isNegative ? "auto" : "-8px",
                      bottom: isNegative ? "-8px" : "auto",
                      background: `${bar.color}66`,
                      transform: "rotateX(90deg)",
                      transformOrigin: "bottom",
                    }}
                  />
                  {/* Label */}
                  <div
                    className="absolute text-center w-full text-xs font-bold font-mono"
                    style={{
                      top: isNegative ? `${height + 5}px` : `-${height + 20}px`,
                      color: bar.color,
                    }}
                  >
                    {bar.label}
                  </div>
                  {/* Value */}
                  <div
                    className="absolute text-center w-full text-[10px] font-mono text-slate-400"
                    style={{
                      top: isNegative ? `${height + 18}px` : `-${height + 32}px`,
                    }}
                  >
                    {bar.value.toFixed(2)}
                  </div>
                </div>
              );
            })}

            {/* Axis labels */}
            <div
              className="absolute text-[10px] font-mono text-slate-500"
              style={{ bottom: "-25px", left: "50%", transform: "translateX(-50%)" }}
            >
              Greeks Exposure
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-2 left-2 flex gap-3">
          {bars.map(b => (
            <div key={b.label} className="flex items-center gap-1">
              <div className="w-2 h-2 rounded" style={{ background: b.color }} />
              <span className="text-[9px] font-mono text-slate-400">{b.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface GreekSurfacePlotProps {
  spotRange: number[];
  dteRange: number[];
  values: number[][];
  label: string;
  colorScheme: "delta" | "gamma" | "theta" | "vega" | "pnl";
}

export function GreekSurfacePlot({ spotRange, dteRange, values, label, colorScheme }: GreekSurfacePlotProps) {
  const [rotation, setRotation] = useState({ x: -30, y: 45 });
  const [isDragging, setIsDragging] = useState(false);
  const [lastPos, setLastPos] = useState({ x: 0, y: 0 });

  const colorMap = {
    delta: ["#1e1b4b", "#10b981", "#34d399"],
    gamma: ["#1e1b4b", "#6366f1", "#a5b4fc"],
    theta: ["#1e1b4b", "#f59e0b", "#fcd34d"],
    vega: ["#1e1b4b", "#ec4899", "#f9a8d4"],
    pnl: ["#f43f5e", "#334155", "#10b981"],
  };

  const colors = colorMap[colorScheme];

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setLastPos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = e.clientX - lastPos.x;
    const dy = e.clientY - lastPos.y;
    setRotation(prev => ({
      x: Math.max(-90, Math.min(90, prev.x - dy * 0.5)),
      y: prev.y + dx * 0.5,
    }));
    setLastPos({ x: e.clientX, y: e.clientY });
  };

  const handleMouseUp = () => setIsDragging(false);

  const flatValues = values.flat();
  const minVal = Math.min(...flatValues);
  const maxVal = Math.max(...flatValues);
  const range = maxVal - minVal || 1;

  const getColor = (val: number) => {
    const t = (val - minVal) / range;
    if (t < 0.5) {
      return colors[0];
    } else if (t < 0.75) {
      return colors[1];
    }
    return colors[2];
  };

  const cellW = 20;
  const cellH = 12;
  const heightScale = 25;

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 bg-slate-950">
        <span className="text-xs text-slate-300 font-semibold uppercase tracking-widest">{label} Surface</span>
        <span className="text-[10px] font-mono text-slate-500">spot x DTE</span>
      </div>
      <div
        className="relative cursor-grab active:cursor-grabbing overflow-hidden"
        style={{ height: 200, perspective: "600px" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: "preserve-3d" }}
        >
          <div
            style={{
              transformStyle: "preserve-3d",
              transform: `rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)`,
            }}
          >
            {values.map((row, i) =>
              row.map((val, j) => {
                const h = ((val - minVal) / range) * heightScale;
                return (
                  <div
                    key={`${i}-${j}`}
                    className="absolute"
                    style={{
                      left: j * cellW - (row.length * cellW) / 2,
                      top: i * cellH - (values.length * cellH) / 2,
                      width: cellW - 1,
                      height: cellH - 1,
                      background: getColor(val),
                      transform: `translateZ(${h}px)`,
                      opacity: 0.9,
                    }}
                  />
                );
              })
            )}
          </div>
        </div>

        {/* Color scale */}
        <div className="absolute bottom-2 right-2 flex items-center gap-1">
          <span className="text-[9px] font-mono text-slate-500">{minVal.toFixed(1)}</span>
          <div className="w-16 h-2 rounded" style={{ background: `linear-gradient(90deg, ${colors.join(",")})` }} />
          <span className="text-[9px] font-mono text-slate-500">{maxVal.toFixed(1)}</span>
        </div>
      </div>
    </div>
  );
}
