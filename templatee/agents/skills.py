"""
OpenCLAW-style skills: explain_formula, interpret_metric, explain_concept,
analyze_workspace_data, and more.
Uses Neo4jKnowledgeClient and OllamaClient (or GroqClient).
"""

import re
import json
from typing import Any, Optional, Union

from app.knowledge_base.neo4j_client import Neo4jKnowledgeClient, KnowledgeNotFoundError
from app.agents.llm_client import OllamaClient

# Frontend menu_id -> Neo4j Menu name
MENU_ID_TO_NAME = {
    "overview": "Portfolio",
    "pricer": "Pricer",
    "portfolio": "Portfolio",
    "risk": "Risk",
    "optimizer": "Optimizer",
    "volatility": "Volatility Lab",
    "factor": "Factor Lab",
    "scenarios": "Scenarios",
    "blotter": "Blotter",
}


def _menu_context(menu_id: Optional[str]) -> Optional[str]:
    if not menu_id:
        return None
    return MENU_ID_TO_NAME.get(menu_id.lower())


def explain_formula(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    formula_name: str,
) -> dict[str, Any]:
    """Skill: explain a pricing/risk formula using Neo4j context + Ollama."""
    formula = kb.get_formula(formula_name)
    if not formula:
        raise KnowledgeNotFoundError(f"Formula not found: {formula_name}")
    eq = formula.get("equation") or ""
    desc = formula.get("description") or ""
    variables = formula.get("variables") or []
    assumptions = formula.get("assumptions") or []
    system = "You are a financial engineering expert. Explain formulas clearly and concisely."
    user = (
        f"Formula: {formula_name}\n"
        f"Equation: {eq}\n"
        f"Description: {desc}\n"
        f"Variables: {', '.join(variables)}\n"
        f"Assumptions: {', '.join(assumptions)}\n\n"
        "Explain this formula in plain language for a practitioner. Keep the response under 300 words."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [{"type": "formula", "name": formula_name}]}


def interpret_metric(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    metric_name: str,
    value: float,
    menu_context: Optional[str] = None,
) -> dict[str, Any]:
    """Skill: interpret a metric value using Neo4j interpretations + Ollama."""
    interps = kb.get_metric_interpretation(metric_name, value, menu_context)
    if not interps:
        system = "You are a portfolio and risk analyst."
        user = (
            f"The user has a metric '{metric_name}' with value {value}. "
            "Provide a brief interpretation and practical guidance. No knowledge base match was found."
        )
        reply = llm.generate(user, system=system, temperature=0.3)
        return {"reply": reply, "sources": []}
    top = interps[0]
    system = "You are a portfolio and risk analyst. Summarize interpretations and advise clearly."
    user = (
        f"Metric: {metric_name}, Value: {value}\n"
        f"Interpretation: {top.get('interpretation')}\n"
        f"Suggested action: {top.get('action')}\n"
        "Summarize this for the user in 2-3 sentences and add one practical tip."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [{"type": "interpretation", "metric": metric_name}]}


def explain_concept(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    concept_name: str,
) -> dict[str, Any]:
    """Skill: explain a financial concept using Neo4j definition + Ollama."""
    concept = kb.get_concept(concept_name)
    if not concept:
        raise KnowledgeNotFoundError(f"Concept not found: {concept_name}")
    definition = concept.get("definition") or ""
    category = concept.get("category") or ""
    system = "You are a financial engineering expert. Explain concepts clearly."
    user = (
        f"Concept: {concept_name}\n"
        f"Definition: {definition}\n"
        f"Category: {category}\n\n"
        "Explain this concept in 2-4 sentences for a practitioner."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [{"type": "concept", "name": concept_name}]}


def get_related_concepts(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    concept_name: str,
    depth: int = 2,
) -> dict[str, Any]:
    """Skill: get related concepts and summarize how they relate."""
    related = kb.get_related_concepts(concept_name, depth=depth)
    if not related:
        base = kb.get_concept(concept_name)
        if not base:
            raise KnowledgeNotFoundError(f"Concept not found: {concept_name}")
        reply = f"No related concepts found in the knowledge graph for '{concept_name}'."
        return {"reply": reply, "sources": [], "related": []}
    system = "You are a financial engineering expert. Briefly explain how these concepts relate."
    items = "\n".join(
        f"- {r['name']}: {r.get('definition', '')[:100]}..." for r in related[:15]
    )
    user = (
        f"Central concept: {concept_name}\nRelated concepts:\n{items}\n\n"
        "In 2-4 sentences, explain how these concepts connect."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [], "related": related}


def compare_formulas(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    name_a: str,
    name_b: str,
) -> dict[str, Any]:
    """Skill: compare two formulas (e.g. BS vs Heston)."""
    fa = kb.get_formula(name_a)
    fb = kb.get_formula(name_b)
    if not fa:
        raise KnowledgeNotFoundError(f"Formula not found: {name_a}")
    if not fb:
        raise KnowledgeNotFoundError(f"Formula not found: {name_b}")
    system = "You are a financial engineering expert. Compare models clearly."
    user = (
        f"Formula A: {name_a}\nEquation: {fa.get('equation')}\nDescription: {fa.get('description')}\n"
        f"Formula B: {name_b}\nEquation: {fb.get('equation')}\nDescription: {fb.get('description')}\n\n"
        "Compare these two: when to use each, key differences, and limitations. Keep under 200 words."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [{"type": "formula", "name": name_a}, {"type": "formula", "name": name_b}]}


def check_assumptions(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    formula_name: str,
) -> dict[str, Any]:
    """Skill: check whether a formula's assumptions are valid in current context."""
    formula = kb.get_formula(formula_name)
    if not formula:
        raise KnowledgeNotFoundError(f"Formula not found: {formula_name}")
    assumptions = formula.get("assumptions") or []
    system = "You are a risk and model validation expert. Assess assumptions critically."
    user = (
        f"Formula: {formula_name}\n"
        f"Assumptions: {', '.join(assumptions)}\n\n"
        "List these assumptions and briefly comment on when they might be violated in practice. Keep under 200 words."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [{"type": "formula", "name": formula_name}]}


def list_menu_concepts(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    menu_name: str,
) -> dict[str, Any]:
    """Skill: list concepts for a menu; optionally summarize via LLM."""
    concepts = kb.get_menu_concepts(menu_name)
    if not concepts:
        reply = f"No concepts found for menu '{menu_name}'."
        return {"reply": reply, "sources": [], "concepts": []}
    system = "You are a financial engineering educator. Summarize briefly."
    items = "\n".join(f"- {c['name']}: {c.get('definition', '')[:80]}..." for c in concepts[:25])
    user = (
        f"Concepts for the {menu_name} module:\n{items}\n\n"
        "Give a one-paragraph overview of what this module covers."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [], "concepts": concepts}


def trace_derivation(
    kb: Neo4jKnowledgeClient,
    llm: OllamaClient,
    formula_name: str,
) -> dict[str, Any]:
    """Skill: trace formula lineage (DERIVES_FROM, USES)."""
    graph = kb.get_formula_derivation_graph(formula_name)
    if not graph or not graph.get("name"):
        raise KnowledgeNotFoundError(f"Formula not found: {formula_name}")
    derives = graph.get("derives_from") or []
    uses = graph.get("uses_concepts") or []
    system = "You are a financial engineering expert. Explain derivation and dependencies."
    user = (
        f"Formula: {formula_name}\nEquation: {graph.get('equation')}\n"
        f"Derives from: {', '.join(derives) or 'none'}\n"
        f"Uses concepts: {', '.join(uses) or 'none'}\n\n"
        "Briefly trace how this formula is derived and what concepts it builds on. Under 200 words."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": [{"type": "formula", "name": formula_name}]}


# ── Per-menu expert system prompts ──────────────────────────────────────────

MENU_SYSTEM_PROMPTS: dict[str, str] = {
    "pricer": (
        "You are a derivatives pricing expert and quantitative analyst with deep knowledge of "
        "Black-Scholes, FFT (Carr-Madan), Heston stochastic volatility, and the full Greeks "
        "(Δ, Γ, Θ, ν, ρ). You analyse pricing results, interpret Greeks in the context of a "
        "live trading position, assess model assumptions, flag when BS breaks down "
        "(vol smile, jumps, short expiry), and give actionable hedging insights. "
        "Reference WQU M1-M2 theory where relevant. Be precise with numbers."
    ),
    "portfolio": (
        "You are a portfolio manager and financial engineer specialising in classical "
        "portfolio theory (Markowitz 1952, CAPM, Black 1972). You interpret portfolio "
        "moments (expected return, variance, volatility, beta, skewness, kurtosis), "
        "performance metrics (Sharpe, Treynor, Sortino, M², Information Ratio, "
        "Jensen α, Appraisal Ratio), and coskewness. You assess diversification, "
        "systematic vs idiosyncratic risk, benchmark tracking, and provide actionable "
        "portfolio construction advice. Reference WQU M1-M2 curriculum."
    ),
    "risk": (
        "You are a quantitative risk manager with expertise in Value at Risk (VaR), "
        "Expected Shortfall (ES/CVaR), covariance estimation (Ledoit-Wolf, OAS shrinkage, "
        "eigenspectrum), minimum spanning trees (Mantegna 1999), and Basel III "
        "capital requirements. You interpret risk metrics with precision, identify "
        "sources of tail risk, assess model risk (parametric vs historical vs MC), "
        "and provide actionable risk-mitigation recommendations. Reference WQU M7."
    ),
    "optimizer": (
        "You are a portfolio optimisation specialist with deep expertise in "
        "Mean-Variance Optimisation (Markowitz QP via cvxpy), Black-Litterman Model "
        "(equilibrium π = δΣw_m, posterior blending views), Critical Line Algorithm, "
        "Kelly Criterion (single- and multi-asset), Equal Risk Contribution / "
        "Relaxed Risk Parity (SOCP), and Hierarchical Risk Parity (Ward clustering + "
        "recursive bisection, Mantegna distance). You evaluate optimised portfolios, "
        "explain weight drivers, compare methodologies, and advise on the best "
        "approach for a given investment mandate. Reference WQU M3-M5-M7."
    ),
    "volatility": (
        "You are a volatility specialist with expertise in implied volatility surfaces, "
        "Heston stochastic volatility model (mean-reversion κ, long-run θ, vol-of-vol σᵥ, "
        "correlation ρ), Feller condition 2κθ > σᵥ², realised vs implied vol analysis, "
        "volatility risk premium (VRP), and term structure dynamics. You interpret "
        "calibrated Heston parameters, identify vol trading opportunities, assess the "
        "vol surface shape (contango, backwardation, smile vs skew), and explain "
        "systematic volatility patterns. Reference WQU M2-M3."
    ),
    "factor": (
        "You are a factor investing specialist with expertise in OLS multi-factor models "
        "(alphas, betas, R², residual variance), Fama-MacBeth two-stage regression "
        "(λ risk premia, t-statistics, p-values), smart beta (quintile sorts, "
        "signal-weighted long-short), factor crowding / herding index, and ML-based "
        "factor discovery. You interpret factor exposures with statistical rigour, "
        "assess alpha significance, identify crowded trades, and advise on factor "
        "portfolio construction. Reference WQU M6."
    ),
    "scenarios": (
        "You are a scenario analysis and stress-testing expert with knowledge of "
        "historical crisis periods (GFC 2008, COVID-19 2020, Quant Meltdown 2007), "
        "probabilistic scenario optimisation, Monte Carlo simulation (multivariate "
        "normal and t-distribution), prospect theory (loss aversion λ, probability "
        "weighting γ), and herding-stressed VaR. You interpret scenario impacts, "
        "quantify tail risks, compare crisis resilience, and provide portfolio "
        "hardening recommendations. Reference WQU M4."
    ),
    "blotter": (
        "You are a senior trade execution and performance attribution specialist "
        "with deep expertise in: (1) P&L decomposition — Jensen α, systematic β·R_m, "
        "factor contributions, and idiosyncratic residual; (2) position monitoring and "
        "mark-to-market accounting; (3) trading edge assessment — win rate, profit "
        "factor, expectancy, and risk-adjusted return; (4) position sizing frameworks — "
        "Kelly criterion (f* = (bp - q)/b), fixed fractional, volatility-adjusted "
        "sizing (σ-target / σ_asset); (5) risk management — stop-loss placement "
        "relative to ATR, profit targets via R-multiple or risk-reward ratio; "
        "(6) exit strategies — trailing stops, time-based exits, mean-reversion exits. "
        "You interpret blotter data to: diagnose P&L attribution by source, identify "
        "positions with negative alpha vs beta drift, recommend position adjustments "
        "based on Kelly-optimal sizing, suggest hedging overlays when β is elevated, "
        "and flag crowding risk. When recommending strategies, cite: "
        "Chan (Quantitative Trading), Hull (Options, Futures & Derivatives), "
        "O'Neil (CAN SLIM), Douglas (Trading in the Zone), Tulchinsky (Finding Alphas). "
        "Format all mathematical expressions in LaTeX. Be specific with numbers."
    ),
    "overview": (
        "You are a full-stack financial engineer with comprehensive expertise across "
        "derivatives pricing, portfolio analytics, risk management, optimisation, "
        "volatility modelling, factor investing, scenario analysis, and trade "
        "execution. You provide holistic, integrated insights that connect theory "
        "across modules and give actionable recommendations grounded in quantitative "
        "finance best practice. Reference WQU M1-M7 curriculum where relevant. "
        "When suggesting trading strategies, cite authoritative sources: Hull (Options/Futures/Derivatives), "
        "Chan (Quantitative Trading), Tulchinsky (Finding Alphas), Baxter & Rennie (Financial Calculus), "
        "Nison (Candlestick Techniques), O'Neil (CAN SLIM), Douglas (Trading Psychology)."
    ),
}

# Book sources available in the knowledge graph
KNOWLEDGE_SOURCES = [
    "Ernest P. Chan — Quantitative Trading (Wiley 2009)",
    "Igor Tulchinsky — Finding Alphas (Wiley 2020)",
    "John C. Hull — Options, Futures and Other Derivatives",
    "Martin Baxter & Andrew Rennie — Financial Calculus (Cambridge 2012)",
    "Steve Nison — Japanese Candlestick Charting Techniques",
    "William J. O'Neil — How To Make Money In Stocks",
    "Springer — Financial Mathematics, Derivatives and Structured Products",
    "Springer — Actuarial Sciences and Quantitative Finance (ICASQF2016)",
    "Mark Douglas — The Disciplined Trader / Trading In the Zone",
    "Valuation and Volatility: Stakeholder's Perspective",
]


def _format_workspace_data(workspace_data: dict[str, Any]) -> str:
    """Format workspace_data dict into a clear, readable summary for the LLM."""
    lines: list[str] = []
    for key, val in workspace_data.items():
        label = key.replace("_", " ").upper()
        if isinstance(val, dict):
            lines.append(f"\n{label}:")
            for k, v in val.items():
                if v is not None:
                    lines.append(f"  {k}: {v}")
        elif isinstance(val, list):
            if len(val) == 0:
                continue
            # Truncate long lists
            preview = val[:12] if len(val) > 12 else val
            try:
                lines.append(f"{label}: {json.dumps(preview, default=str)}")
            except Exception:
                lines.append(f"{label}: [list of {len(val)} items]")
        elif val is not None:
            lines.append(f"{label}: {val}")
    return "\n".join(lines) if lines else "No computed data available yet."


def analyze_workspace_data(
    llm: Union[OllamaClient, Any],
    menu_id: Optional[str],
    message: str,
    workspace_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyse actual computed workspace data as a full-stack financial engineer.
    Does NOT require Neo4j — pure LLM analysis of real numbers.
    Called when context['workspace_data'] is present.
    """
    menu_name = MENU_ID_TO_NAME.get((menu_id or "").lower(), "Transact Platform")
    system = MENU_SYSTEM_PROMPTS.get((menu_id or "").lower(), MENU_SYSTEM_PROMPTS["overview"])
    data_summary = _format_workspace_data(workspace_data)

    user = (
        f"Module: {menu_name}\n"
        f"Computed results from the workspace:\n"
        f"{data_summary}\n\n"
        f"User question: {message}\n\n"
        f"STRICT RULES — you MUST follow these:\n"
        f"1. Base your entire analysis on the ACTUAL computed values shown above. Do NOT invent, assume, or substitute hypothetical numbers.\n"
        f"2. If a metric is shown (e.g. Return=83.15%, Sharpe=-1.735), reference THAT exact value in your response.\n"
        f"3. If the user asks to compare models (e.g. BS vs Heston), use the ACTUAL model prices shown — do not fabricate example parameters.\n"
        f"4. If no computed data is available for a sub-question, say 'Run the analysis first to see the computed values' — do not fill in with examples.\n"
        f"5. Format ALL mathematical formulas in LaTeX: use $...$ for inline math, $$...$$ or \\[...\\] for display equations.\n\n"
        f"Now provide expert financial engineering analysis: interpret the specific numbers, explain implications for a practitioner, "
        f"identify key risks and opportunities, and give concrete actionable recommendations grounded in the actual computed results."
    )

    reply = llm.generate(user, system=system, temperature=0.35)
    return {
        "reply": reply,
        "sources": [{"type": "workspace_analysis", "menu": menu_id or "overview"}],
    }


def route_and_run(
    kb: Optional[Neo4jKnowledgeClient],
    llm: Union[OllamaClient, Any],
    message: str,
    menu_id: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Classify user message and dispatch to the appropriate skill.
    context may contain:
      - workspace_data: dict of computed results from the current workspace (no kb needed)
      - metric_name, metric_value, formula_name, concept_name: explicit routing hints
    kb may be None when workspace_data is present and Neo4j is unavailable.
    """
    context = context or {}
    msg = (message or "").strip().lower()
    menu_name = _menu_context(menu_id)

    # ── Highest priority: workspace data analysis (no kb required) ─────────────
    if context.get("workspace_data") and isinstance(context["workspace_data"], dict):
        workspace_data = context["workspace_data"]
        # If the question is strategy-related, blend workspace analysis with strategy KB
        if kb and _is_strategy_question(msg):
            return suggest_trading_strategies(kb, llm, message or "Suggest strategies", menu_id, workspace_data)
        return analyze_workspace_data(llm, menu_id, message or "Analyse my current results", workspace_data)

    # For all skill-based routing below, kb is required
    if kb is None:
        # No knowledge base and no workspace data — give a helpful generic reply
        system = MENU_SYSTEM_PROMPTS.get((menu_id or "").lower(), MENU_SYSTEM_PROMPTS["overview"])
        menu_display = MENU_ID_TO_NAME.get((menu_id or "").lower(), "the platform")
        user = (
            f"Module: {menu_display}\n"
            f"User question: {message}\n\n"
            "Answer this financial question helpfully and precisely. "
            "Reference relevant quantitative finance theory where appropriate. "
            "Format all mathematical formulas in LaTeX: use $...$ for inline math, $$...$$ or \\[...\\] for display equations. "
            "If the question is about specific portfolio/option results, remind the user to run the analysis "
            "in the workspace first so you can analyse their actual computed numbers."
        )
        reply = llm.generate(user, system=system, temperature=0.35)
        return {"reply": reply, "sources": []}

    # Explicit context from frontend
    if context.get("formula_name"):
        return explain_formula(kb, llm, context["formula_name"])
    if context.get("metric_name") is not None and context.get("metric_value") is not None:
        return interpret_metric(
            kb, llm,
            context["metric_name"],
            float(context["metric_value"]),
            menu_name,
        )
    if context.get("concept_name"):
        return explain_concept(kb, llm, context["concept_name"])

    # Strategy suggestion routing (before formula/concept routing)
    if _is_strategy_question(msg):
        return suggest_trading_strategies(kb, llm, message, menu_id)

    # Heuristic routing from message text
    if "compare" in msg or " vs " in msg or " versus " in msg:
        if "black-scholes" in msg or "bs " in msg and "heston" in msg:
            return compare_formulas(kb, llm, "Black-Scholes Call", "Heston Call")
        if "var" in msg and "es" in msg:
            return compare_formulas(kb, llm, "VaR Parametric Normal", "Expected Shortfall (ES)")
    if "assumption" in msg or "valid" in msg:
        if "black-scholes" in msg or " bs " in msg:
            return check_assumptions(kb, llm, "Black-Scholes Call")
        if "heston" in msg:
            return check_assumptions(kb, llm, "Heston Call")
        if "var" in msg:
            return check_assumptions(kb, llm, "VaR Parametric Normal")
        if "kelly" in msg:
            return check_assumptions(kb, llm, "Kelly Criterion (Single)")
    if "derive" in msg or "derivation" in msg or "lineage" in msg:
        if "black-litterman" in msg or "blm" in msg:
            return trace_derivation(kb, llm, "Black-Litterman Posterior")
        if "black-scholes" in msg or "bs" in msg:
            return trace_derivation(kb, llm, "Black-Scholes Call")
        if "kelly" in msg:
            return trace_derivation(kb, llm, "Kelly Criterion (Single)")
    if "related" in msg or "relate" in msg:
        # Try to find a concept name (simplified: use last quoted or last word sequence)
        concept = _extract_concept(message)
        if concept:
            return get_related_concepts(kb, llm, concept)
    if "list" in msg or "concept" in msg and ("menu" in msg or "module" in msg):
        if menu_name:
            return list_menu_concepts(kb, llm, menu_name)
    if "interpret" in msg or "what does" in msg or "mean" in msg:
        # Try metric + value
        metric, value = _extract_metric_value(message)
        if metric and value is not None:
            return interpret_metric(kb, llm, metric, value, menu_name)
    # Formula explain: "explain black-scholes", "what is heston"
    formula = _extract_formula(message)
    if formula:
        return explain_formula(kb, llm, formula)
    # Concept explain: "what is VaR", "explain Sharpe"
    concept = _extract_concept(message)
    if concept:
        return explain_concept(kb, llm, concept)
    # Default: list menu concepts if we have a menu, else generic reply
    if menu_name:
        return list_menu_concepts(kb, llm, menu_name)
    system = "You are a financial engineering assistant for a portfolio and derivatives platform."
    user = (
        "The user asked something that could not be matched to a specific skill. "
        "Reply briefly that you can explain formulas (e.g. Black-Scholes, Heston), "
        "interpret metrics (e.g. Sharpe ratio, VaR), explain concepts, or list concepts by module. "
        "Ask them to try a more specific question or use the context buttons."
    )
    reply = llm.generate(user, system=system, temperature=0.3)
    return {"reply": reply, "sources": []}


def suggest_trading_strategies(
    kb: Neo4jKnowledgeClient,
    llm: Union[OllamaClient, Any],
    message: str,
    menu_id: Optional[str] = None,
    workspace_data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Skill: suggest relevant trading strategies from the knowledge graph.

    Queries TradingStrategy nodes by keyword (extracted from message) + menu context.
    Grounds the LLM response in actual book-sourced strategies — reduces hallucination.
    """
    menu_name = _menu_context(menu_id)

    # Extract keyword from message for targeted search
    kw = _extract_strategy_keyword(message)

    strategies = kb.search_trading_strategies(
        keyword=kw or None,
        menu_name=menu_name,
        limit=6,
    )

    # Fall back to menu-only search if keyword search returned nothing
    if not strategies and menu_name:
        strategies = kb.get_strategies_for_menu(menu_name, limit=6)

    # Format strategies for LLM context
    if strategies:
        strat_context = "\n\n".join(
            f"**{s['name']}** [{s.get('category', '')}]\n"
            f"Source: {s.get('book_source', 'Unknown')} by {s.get('book_author', '')}\n"
            f"Description: {s.get('description', '')}\n"
            f"Entry: {s.get('entry_signal', 'N/A')}\n"
            f"Exit: {s.get('exit_signal', 'N/A')}\n"
            f"Risk Management: {s.get('risk_management', 'N/A')}\n"
            f"Timeframe: {s.get('timeframe', 'N/A')} | Asset Class: {s.get('asset_class', 'N/A')}"
            for s in strategies
        )
        sources = [
            {"type": "trading_strategy", "name": s["name"], "book": s.get("book_source", "")}
            for s in strategies
        ]
    else:
        strat_context = "No strategies found in the knowledge base for this query."
        sources = []

    system = MENU_SYSTEM_PROMPTS.get((menu_id or "").lower(), MENU_SYSTEM_PROMPTS["overview"])

    # Include workspace data if available for contextual recommendations
    workspace_ctx = ""
    if workspace_data:
        data_summary = _format_workspace_data(workspace_data)
        workspace_ctx = (
            f"\nCurrent workspace data (use these actual numbers for contextual strategy recommendations):\n"
            f"{data_summary}\n"
        )

    user = (
        f"The user asks: {message}\n\n"
        f"Relevant trading strategies from the knowledge base (sourced from authoritative texts):\n\n"
        f"{strat_context}\n"
        f"{workspace_ctx}\n"
        f"As a financial engineer, recommend the most appropriate strategies for the user's situation.\n"
        f"RULES:\n"
        f"1. Only reference the strategies shown above — these are grounded in the cited books.\n"
        f"2. If workspace data is shown, tailor recommendations to the specific portfolio/position.\n"
        f"3. Format mathematical signals in LaTeX: use $...$ for inline math, $$...$$ or \\[...\\] for display equations.\n"
        f"4. Cite the book source for each strategy mentioned (e.g., 'Hull (Options, Futures & Derivatives)').\n"
        f"5. Be specific: explain entry/exit rules and risk management concretely.\n"
    )

    reply = llm.generate(user, system=system, temperature=0.35)
    return {"reply": reply, "sources": sources}


def _is_strategy_question(msg: str) -> bool:
    """Return True if the message is asking for trading strategy suggestions."""
    strategy_triggers = [
        "strateg", "suggest", "recommend", "which strategy", "what strategy",
        "how to trade", "how should i trade", "what should i", "trading approach",
        "trading idea", "trading plan", "signal", "entry", "exit", "when to buy",
        "when to sell", "how to play", "how to position", "tactical",
        # Blotter-specific triggers
        "position size", "stop loss", "stop-loss", "profit target", "cut loss",
        "add to position", "reduce position", "hedge", "rebalance",
        "kelly", "sizing", "risk-reward", "r-multiple", "drawdown limit",
        "attribution", "improve alpha", "beat beta", "underperform",
    ]
    return any(t in msg for t in strategy_triggers)


def _extract_strategy_keyword(message: str) -> str:
    """Extract the most relevant keyword from a strategy-related question."""
    msg = message.lower()
    # Strategy-specific terms
    strategy_terms = [
        "momentum", "mean reversion", "pairs trading", "arbitrage", "volatility",
        "options", "delta", "gamma", "theta", "covered call", "straddle", "condor",
        "calendar spread", "breakout", "trend following", "factor", "alpha", "kelly",
        "risk parity", "black-litterman", "HRP", "drawdown", "VaR", "hedging",
        "candlestick", "engulfing", "doji", "moving average", "MACD", "RSI",
        "bollinger", "CAN SLIM", "growth", "position sizing", "structured product",
        "barrier", "real option", "volatility arbitrage", "gamma scalping",
        # Blotter terms
        "stop loss", "stop-loss", "profit target", "trailing stop", "fixed fractional",
        "volatility targeting", "risk-reward", "r-multiple", "attribution",
        "cut loss", "add to position", "reduce exposure", "hedge overlay",
    ]
    for term in strategy_terms:
        if term in msg:
            return term
    # Fall back: extract significant words (skip common words)
    stop_words = {"what", "how", "should", "i", "my", "the", "a", "an", "is", "are",
                  "can", "for", "to", "do", "use", "give", "me", "suggest", "strategy",
                  "strategies", "trading", "which", "best", "good", "recommend"}
    words = [w for w in msg.split() if len(w) > 3 and w not in stop_words]
    return words[0] if words else ""


def enrich_graph_from_feedback(
    kb: Neo4jKnowledgeClient,
    llm: Union[OllamaClient, Any],
    limit: int = 30,
) -> dict[str, Any]:
    """
    RLHF GraphRAG enrichment pass.

    1. Fetches recent low-rated (<=2) feedback with user corrections from Neo4j.
    2. Asks the LLM to propose improved interpretations / new concepts.
    3. Writes improvements back to Neo4j via upsert_enriched_* methods.

    Called from POST /agents/enrich (background or manual trigger).
    Returns a summary of changes made.
    """
    bad_feedback = [
        f for f in kb.get_recent_feedback(limit=limit)
        if f.get("rating", 3) <= 2 and f.get("corrected_reply")
    ]
    if not bad_feedback:
        return {"enriched": 0, "summary": "No actionable negative feedback found."}

    enriched = 0
    summaries: list[str] = []

    for fb in bad_feedback[:10]:  # cap at 10 per pass to stay within LLM budget
        menu_id = fb.get("menu_id", "overview")
        system = MENU_SYSTEM_PROMPTS.get(menu_id, MENU_SYSTEM_PROMPTS["overview"])
        user = (
            f"A user rated this agent response as poor (rating {fb['rating']}/5).\n"
            f"Original question: {fb['user_message']}\n"
            f"Incorrect response: {fb['agent_reply']}\n"
            f"User correction: {fb['corrected_reply']}\n\n"
            "Extract 1-3 key facts or improved interpretations from the correction "
            "that should be stored in the knowledge graph. "
            "Format as a JSON array, each item with keys: "
            "type ('concept' or 'metric_interpretation'), name, "
            "definition_or_interpretation, action (for metric_interpretation only), "
            "confidence (0.0-1.0). Output ONLY valid JSON, nothing else."
        )
        raw = llm.generate(user, system=system, temperature=0.2)
        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                items = [items]
            menu_name = MENU_ID_TO_NAME.get(menu_id, "Portfolio")
            for item in items:
                t = item.get("type", "")
                if t == "concept" and item.get("name") and item.get("definition_or_interpretation"):
                    kb.upsert_enriched_concept(
                        name=item["name"],
                        definition=item["definition_or_interpretation"],
                        category=item.get("category", "general"),
                        menu_name=menu_name,
                        source="rlhf_feedback",
                    )
                    enriched += 1
                    summaries.append(f"Updated concept '{item['name']}' ({menu_name})")
                elif t == "metric_interpretation" and item.get("name"):
                    kb.upsert_enriched_interpretation(
                        metric_name=item["name"],
                        condition=item.get("condition", "general"),
                        interpretation=item["definition_or_interpretation"],
                        action=item.get("action", "Review this metric carefully."),
                        confidence=float(item.get("confidence", 0.7)),
                        menu_context=menu_name,
                        source="rlhf_feedback",
                    )
                    enriched += 1
                    summaries.append(f"Updated metric interpretation for '{item['name']}' ({menu_name})")
        except (json.JSONDecodeError, Exception):
            pass  # Malformed JSON from LLM — skip

    return {
        "enriched": enriched,
        "summary": "; ".join(summaries) if summaries else "No enrichments applied this pass.",
    }


def _title(s: str) -> str:
    """Map keyword to display-style name (used for concept/formula hints)."""
    if s == "bs":
        return "Black-Scholes Call"
    if s == "var":
        return "VaR Parametric Normal"
    return s.replace("-", " ").title()


def _extract_formula(message: str) -> Optional[str]:
    """Simple extraction of formula name from message."""
    msg = (message or "").strip()
    lower = msg.lower()
    if "black-scholes" in lower or "black scholes" in lower:
        return "Black-Scholes Call"
    if "heston" in lower:
        return "Heston Call"
    if "kelly" in lower:
        return "Kelly Criterion (Single)"
    if "var" in lower and "expected shortfall" not in lower:
        return "VaR Parametric Normal"
    if "blm" in lower or "black-litterman" in lower:
        return "Black-Litterman Posterior"
    if "sharpe" in lower:
        return "Sharpe Ratio"
    return None


def _extract_concept(message: str) -> Optional[str]:
    """Extract concept name from message (simplified)."""
    # Could use NER or LLM; for MVP use keywords
    lower = (message or "").lower()
    mapping = {
        "var": "Value at Risk",
        "value at risk": "Value at Risk",
        "sharpe": "Sharpe Ratio",
        "volatility": "Implied Volatility",
        "implied vol": "Implied Volatility",
        "delta": "Delta",
        "gamma": "Gamma",
        "vega": "Vega",
        "black-litterman": "Black-Litterman Model",
        "kelly": "Kelly Criterion",
        "risk parity": "Risk Parity",
        "hrp": "Hierarchical Risk Parity",
    }
    for k, v in mapping.items():
        if k in lower:
            return v
    return None


def _extract_metric_value(message: str) -> tuple[Optional[str], Optional[float]]:
    """Try to extract metric name and numeric value from message."""
    lower = (message or "").lower()
    metric = None
    if "sharpe" in lower:
        metric = "Sharpe Ratio"
    elif "sortino" in lower:
        metric = "Sortino Ratio"
    elif "var" in lower or "var " in lower:
        metric = "VaR (95%)"
    elif "beta" in lower:
        metric = "Beta"
    if not metric:
        return None, None
    # Simple number extraction
    numbers = re.findall(r"-?\d+\.?\d*", message)
    if numbers:
        try:
            return metric, float(numbers[0])
        except ValueError:
            pass
    return metric, None
