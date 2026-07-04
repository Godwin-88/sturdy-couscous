// GraphAlpha Context Menu Provider
// Right-click on any chart element to analyze in Analytics Workspace

import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import {
  BarChart2, TrendingUp, Activity, ShieldAlert, Brain,
  ExternalLink, Copy, Download, Pin,
} from "lucide-react";

interface ContextMenuProps {
  /** The container element to attach the context menu listener to */
  containerRef: React.RefObject<HTMLElement | null>;
  /** Callback when a series needs to be analyzed in the workspace */
  onAnalyze?: (series: ContextMenuSeries) => void;
  /** Callback when a series should be compared */
  onCompare?: (series: ContextMenuSeries) => void;
  /** Callback to create a hypothesis from the series */
  onCreateHypothesis?: (series: ContextMenuSeries) => void;
  /** Callback to pin evidence to an existing hypothesis */
  onPinToHypothesis?: (series: ContextMenuSeries) => void;
}

export interface ContextMenuSeries {
  id: string;
  name: string;
  ticker: string;
  metric: string;
  source: string;
  startDate?: string;
  endDate?: string;
  value?: number;
}

interface MenuState {
  visible: boolean;
  x: number;
  y: number;
  series: ContextMenuSeries | null;
}

export default function ContextMenu({
  containerRef,
  onAnalyze,
  onCompare,
  onCreateHypothesis,
  onPinToHypothesis,
}: ContextMenuProps) {
  const [menu, setMenu] = useState<MenuState>({ visible: false, x: 0, y: 0, series: null });
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const handleContextMenu = useCallback((e: MouseEvent) => {
    // Find the closest element with data-series-id attribute
    const target = (e.target as HTMLElement).closest("[data-series-id]");
    if (!target) {
      setMenu(s => ({ ...s, visible: false }));
      return;
    }

    e.preventDefault();
    e.stopPropagation();

    const seriesId = target.getAttribute("data-series-id") || "";
    const seriesName = target.getAttribute("data-series-name") || seriesId;
    const seriesTicker = target.getAttribute("data-series-ticker") || "";
    const seriesMetric = target.getAttribute("data-series-metric") || "price";
    const seriesSource = target.getAttribute("data-series-source") || "yfinance";
    const seriesStart = target.getAttribute("data-series-start") || undefined;
    const seriesEnd = target.getAttribute("data-series-end") || undefined;
    const seriesVal = target.getAttribute("data-series-value") || undefined;

    setMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      series: {
        id: seriesId,
        name: seriesName,
        ticker: seriesTicker,
        metric: seriesMetric,
        source: seriesSource,
        startDate: seriesStart,
        endDate: seriesEnd,
        value: seriesVal ? parseFloat(seriesVal) : undefined,
      },
    });
  }, []);

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
      setMenu(s => ({ ...s, visible: false }));
    }
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    el.addEventListener("contextmenu", handleContextMenu);
    document.addEventListener("click", handleClickOutside);
    document.addEventListener("scroll", () => setMenu(s => ({ ...s, visible: false })), true);

    return () => {
      el.removeEventListener("contextmenu", handleContextMenu);
      document.removeEventListener("click", handleClickOutside);
      document.removeEventListener("scroll", () => setMenu(s => ({ ...s, visible: false })), true);
    };
  }, [containerRef, handleContextMenu, handleClickOutside]);

  if (!menu.visible || !menu.series) return null;

  const actions = [
    {
      label: "Analyze in Workspace",
      icon: <BarChart2 size={13} />,
      sub: ["Descriptive", "Run full stack (all tiers)"],
      onClick: () => {
        const series = menu.series!;
        navigate(`/analytics?series=${encodeURIComponent(series.id)}&start=${series.startDate || ""}&end=${series.endDate || ""}`);
        onAnalyze?.(series);
        setMenu(s => ({ ...s, visible: false }));
      },
    },
    {
      label: "Compare with...",
      icon: <Activity size={13} />,
      sub: ["Add to active analysis", "Open side-by-side"],
      onClick: () => {
        onCompare?.(menu.series!);
        setMenu(s => ({ ...s, visible: false }));
      },
    },
    {
      label: "Create Hypothesis",
      icon: <Brain size={13} />,
      sub: [`"${menu.series.ticker} signal predicts return"`],
      onClick: () => {
        onCreateHypothesis?.(menu.series!);
        setMenu(s => ({ ...s, visible: false }));
      },
    },
    {
      label: "Pin to Hypothesis Board",
      icon: <Pin size={13} />,
      sub: [],
      onClick: () => {
        onPinToHypothesis?.(menu.series!);
        setMenu(s => ({ ...s, visible: false }));
      },
    },
    {
      label: "Export series as CSV",
      icon: <Download size={13} />,
      sub: [],
      onClick: () => {
        const series = menu.series!;
        const url = `http://localhost:8000/analytics/data?series_id=${encodeURIComponent(series.id)}&format=csv`;
        window.open(url, "_blank");
        setMenu(s => ({ ...s, visible: false }));
      },
    },
    {
      label: "Copy series ID",
      icon: <Copy size={13} />,
      sub: [],
      onClick: () => {
        navigator.clipboard.writeText(menu.series!.id);
        setMenu(s => ({ ...s, visible: false }));
      },
    },
  ];

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[9999] min-w-[240px] bg-slate-900 border border-slate-700 rounded-xl shadow-2xl shadow-black/50 py-1"
      style={{ left: menu.x, top: menu.y }}
    >
      {/* Series header */}
      <div className="px-3 py-2 border-b border-slate-700">
        <div className="text-xs font-mono text-indigo-400 font-semibold">{menu.series.name}</div>
        <div className="text-[10px] font-mono text-slate-500">
          {menu.series.ticker} · {menu.series.metric} · {menu.series.source}
        </div>
      </div>

      {/* Actions */}
      <div className="py-1">
        {actions.map((a, i) => (
          <button
            key={i}
            onClick={a.onClick}
            className={clsx(
              "w-full flex items-center gap-2 px-3 py-1.5 text-xs font-mono",
              "hover:bg-slate-800 text-slate-300 hover:text-slate-100 transition-colors text-left"
            )}
          >
            <span className="text-slate-500 shrink-0">{a.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="truncate">{a.label}</div>
              {a.sub.length > 0 && (
                <div className="text-[10px] text-slate-600 truncate">{a.sub.join(" · ")}</div>
              )}
            </div>
            <ExternalLink size={10} className="text-slate-600 shrink-0" />
          </button>
        ))}
      </div>
    </div>,
    document.body
  );
}