import { usePolling } from "../hooks/usePolling";
import { agentApi, type NewsResult, type MacroResult, type MacroEvent } from "../lib/api";

const IMPACT_COLOR: Record<string, string> = {
  HIGH:   "bg-red-900/60 text-red-300 border border-red-700",
  MEDIUM: "bg-amber-900/50 text-amber-300 border border-amber-700",
  LOW:    "bg-slate-700 text-slate-300 border border-slate-600",
};

function SentimentBar({ value }: { value: number }) {
  const pct  = Math.abs(value) * 50;      // 0–50%
  const bull = value >= 0;
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="relative flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`absolute top-0 h-full rounded-full transition-all ${
            bull ? "right-1/2 bg-emerald-500" : "left-1/2 bg-red-500"
          }`}
          style={{ width: `${pct}%` }}
        />
        <div className="absolute left-1/2 top-0 h-full w-px bg-slate-500" />
      </div>
      <span className={`text-xs font-mono w-12 text-right ${bull ? "text-emerald-400" : "text-red-400"}`}>
        {value >= 0 ? "+" : ""}{value.toFixed(3)}
      </span>
    </div>
  );
}

function NewsSection({ data }: { data: NewsResult | null | undefined }) {
  if (!data) return (
    <div className="text-slate-500 text-sm p-4">Waiting for news agent cycle…</div>
  );

  const tickers  = Object.entries(data.ticker_sentiment).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const concepts = Object.entries(data.concept_sentiment).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

  return (
    <div className="space-y-4">
      {/* Top headlines */}
      {data.top_headlines.length > 0 && (
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wide mb-2 font-semibold">
            Top Headlines ({data.articles} articles)
          </div>
          <ul className="space-y-1">
            {data.top_headlines.map((h, i) => (
              <li key={i} className="text-sm text-slate-300 leading-snug border-l-2 border-slate-600 pl-2 py-0.5">
                {h}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* Ticker sentiment */}
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wide mb-2 font-semibold">
            Ticker Sentiment
          </div>
          {tickers.length === 0
            ? <div className="text-slate-500 text-xs">No ticker mentions</div>
            : (
            <div className="space-y-2">
              {tickers.map(([tk, score]) => (
                <div key={tk} className="flex items-center gap-2">
                  <span className="text-xs font-mono text-slate-200 w-14 shrink-0">{tk}</span>
                  <SentimentBar value={score} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Concept sentiment */}
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wide mb-2 font-semibold">
            Concept Sentiment
          </div>
          {concepts.length === 0
            ? <div className="text-slate-500 text-xs">No concept mentions</div>
            : (
            <div className="space-y-2">
              {concepts.map(([concept, score]) => (
                <div key={concept} className="flex items-center gap-2">
                  <span className="text-xs text-slate-300 w-28 shrink-0 leading-tight">{concept}</span>
                  <SentimentBar value={score} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MacroSection({ data }: { data: MacroResult | null | undefined }) {
  if (!data) return (
    <div className="text-slate-500 text-sm p-4">Waiting for macro calendar cycle…</div>
  );

  const preSignals = Object.entries(data.pre_event_signals);

  return (
    <div className="space-y-4">
      {/* Pre-event signals */}
      {preSignals.length > 0 && (
        <div className="rounded-lg bg-amber-950/40 border border-amber-800/60 p-3">
          <div className="text-xs text-amber-400 font-semibold uppercase tracking-wide mb-2">
            ⚠ Active Pre-Event Size Reductions
          </div>
          <div className="flex flex-wrap gap-2">
            {preSignals.map(([concept, mod]) => (
              <span key={concept} className="text-xs bg-amber-900/60 text-amber-200 border border-amber-700 rounded px-2 py-0.5">
                {concept}: {(mod * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Upcoming events */}
      <div>
        <div className="text-xs text-slate-400 uppercase tracking-wide mb-2 font-semibold">
          Upcoming Events ({data.events} total)
        </div>
        {data.upcoming.length === 0
          ? <div className="text-slate-500 text-xs">No events in lookahead window</div>
          : (
          <div className="space-y-2">
            {data.upcoming.map((e: MacroEvent, i: number) => (
              <div key={i} className="flex items-start gap-3 p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                <div className="text-xs font-mono text-slate-400 shrink-0 mt-0.5">{e.date}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-slate-200 font-medium">{e.name}</div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {e.concepts.map(c => (
                      <span key={c} className="text-xs bg-slate-700 text-slate-400 rounded px-1.5 py-0.5">{c}</span>
                    ))}
                  </div>
                </div>
                <span className={`text-xs rounded px-2 py-0.5 font-semibold shrink-0 ${IMPACT_COLOR[e.impact] ?? IMPACT_COLOR.LOW}`}>
                  {e.impact}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function IntelligencePanel() {
  const { data: news }  = usePolling<NewsResult>(() => agentApi.newsLatest(), 60_000);
  const { data: macro } = usePolling<MacroResult>(() => agentApi.macroLatest(), 300_000);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-4">
      {/* News Sentiment */}
      <div className="bg-slate-800/60 rounded-xl border border-slate-700/60 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📰</span>
          <h2 className="text-base font-semibold text-slate-100">News Sentiment</h2>
          <span className="ml-auto text-xs text-slate-500">refreshes every 60 s</span>
        </div>
        <NewsSection data={news} />
      </div>

      {/* Macro Calendar */}
      <div className="bg-slate-800/60 rounded-xl border border-slate-700/60 p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📅</span>
          <h2 className="text-base font-semibold text-slate-100">Macro Calendar</h2>
          <span className="ml-auto text-xs text-slate-500">refreshes every 5 min</span>
        </div>
        <MacroSection data={macro} />
      </div>
    </div>
  );
}
