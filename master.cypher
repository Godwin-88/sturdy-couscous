// =============================================================================
// GRAPHALPHA — MASTER KNOWLEDGE GRAPH
// Neo4j 5-compatible Cypher (migrated from Memgraph)
// Schema version: 0.2.0
// Changelog:
//   0.2.0 — Added factor investing, asset pricing, risk metrics, estimation,
//            dimensionality reduction, performance attribution, statistics categories.
//            36 new Concept nodes. 7 new Formula nodes. 3 new Strategy nodes.
//            Extended PREREQ_OF, ACTIVATED_BY, CONTRADICTED_BY chains.
//   0.1.0 — Initial seed: options, derivatives, volatility, Greeks (29 concepts)
// =============================================================================
// NODE LABELS
//   Concept          — quant finance concept (from KG seed)
//   Category         — concept grouping (option_pricing, hedging, etc.)
//   Formula          — mathematical formula attached to a concept
//   Strategy         — tradeable strategy node (instantiated from Concepts)
//   Parameter        — named parameter within a formula or strategy
//   Regime           — detected market regime (Trending, MeanReverting, HighVol, etc.) — 8 total
//   Signal           — live runtime signal emitted by the agent
//   Ticker           — xStock/equity instrument
//   Position         — open trade position
//   EarningsEvent    — earnings call event (from Speechmatics ingestion)
//   NewsEntity       — named entity extracted from news/transcripts
//
// RELATIONSHIP TYPES
//   PREREQ_OF          (Concept)->(Concept)         prerequisite chain
//   BELONGS_TO         (Concept)->(Category)        taxonomy grouping
//   HAS_FORMULA        (Concept|Strategy)->(Formula) formula attachment
//   USES_PARAM         (Formula)->(Parameter)        formula parameters
//   DERIVED_FROM       (Strategy)->(Concept)         strategy grounded in concept
//   ACTIVATED_BY       (Strategy)->(Regime)          strategy fires in this regime
//   CONTRADICTED_BY    (Strategy)->(Strategy)        two strategies conflict
//   CORRELATED_WITH    (Ticker)->(Ticker)            price correlation (weighted)
//   HAS_SIGNAL         (Strategy)->(Signal)          emitted runtime signal
//   TARGETS            (Signal)->(Ticker)            signal points at instrument
//   OPENS              (Signal)->(Position)          signal opened this position
//   MENTIONS           (EarningsEvent|NewsEntity)->(Ticker)  ingestion → instrument
//   UPDATES            (EarningsEvent|NewsEntity)->(Signal)  ingestion triggers re-score
//   BELONGS_TO_SECTOR  (Ticker)->(Category)          sector taxonomy
// =============================================================================


// -----------------------------------------------------------------------------
// 0. CONSTRAINTS & INDEXES
// -----------------------------------------------------------------------------

CREATE CONSTRAINT concept_name      IF NOT EXISTS FOR (c:Concept)    REQUIRE c.name   IS UNIQUE;
CREATE CONSTRAINT category_name     IF NOT EXISTS FOR (cat:Category) REQUIRE cat.name IS UNIQUE;
CREATE CONSTRAINT formula_id        IF NOT EXISTS FOR (f:Formula)    REQUIRE f.id     IS UNIQUE;
CREATE CONSTRAINT strategy_name     IF NOT EXISTS FOR (s:Strategy)   REQUIRE s.name   IS UNIQUE;
CREATE CONSTRAINT regime_name       IF NOT EXISTS FOR (r:Regime)     REQUIRE r.name   IS UNIQUE;
CREATE CONSTRAINT ticker_symbol     IF NOT EXISTS FOR (t:Ticker)     REQUIRE t.symbol IS UNIQUE;
CREATE CONSTRAINT signal_id         IF NOT EXISTS FOR (sig:Signal)   REQUIRE sig.id   IS UNIQUE;
CREATE CONSTRAINT position_id       IF NOT EXISTS FOR (p:Position)   REQUIRE p.id     IS UNIQUE;

CREATE INDEX concept_category   IF NOT EXISTS FOR (c:Concept) ON (c.category);
CREATE INDEX concept_difficulty IF NOT EXISTS FOR (c:Concept) ON (c.difficulty);
CREATE INDEX signal_created_at  IF NOT EXISTS FOR (s:Signal)  ON (s.created_at);
CREATE INDEX signal_status      IF NOT EXISTS FOR (s:Signal)  ON (s.status);
CREATE INDEX position_status    IF NOT EXISTS FOR (p:Position) ON (p.status);


// -----------------------------------------------------------------------------
// 1. CATEGORY NODES
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'option_pricing',       display: 'Option Pricing'});
MERGE (:Category {name: 'derivatives',          display: 'Derivatives'});
MERGE (:Category {name: 'volatility',           display: 'Volatility'});
MERGE (:Category {name: 'risk_management',      display: 'Risk Management'});
MERGE (:Category {name: 'hedging',              display: 'Hedging'});
MERGE (:Category {name: 'trading_strategy',     display: 'Trading Strategy'});
MERGE (:Category {name: 'arbitrage',            display: 'Arbitrage'});
MERGE (:Category {name: 'measure_theory',       display: 'Measure Theory'});
MERGE (:Category {name: 'stochastic_processes', display: 'Stochastic Processes'});
MERGE (:Category {name: 'numerical_methods',    display: 'Numerical Methods'});
MERGE (:Category {name: 'mathematical_finance', display: 'Mathematical Finance'});
MERGE (:Category {name: 'exotic_derivatives',   display: 'Exotic Derivatives'});
MERGE (:Category {name: 'greeks',               display: 'Greeks'});
MERGE (:Category {name: 'factor_investing',         display: 'Factor Investing'});
MERGE (:Category {name: 'asset_pricing',            display: 'Asset Pricing'});
MERGE (:Category {name: 'risk_metrics',             display: 'Risk Metrics'});
MERGE (:Category {name: 'estimation',               display: 'Estimation'});
MERGE (:Category {name: 'dimensionality_reduction', display: 'Dimensionality Reduction'});
MERGE (:Category {name: 'performance_attribution',  display: 'Performance Attribution'});
MERGE (:Category {name: 'statistics',               display: 'Statistics'});


// -----------------------------------------------------------------------------
// 2. MARKET REGIME NODES
// -----------------------------------------------------------------------------

MERGE (:Regime {name: 'Trending',        description: 'Strong directional momentum, low mean-reversion',    momentum_score: 0.8, vol_level: 'medium'});
MERGE (:Regime {name: 'MeanReverting',   description: 'Oscillating prices, high autocorrelation reversal',  momentum_score: 0.2, vol_level: 'low'});
MERGE (:Regime {name: 'HighVolatility',  description: 'Elevated realized vol, regime uncertainty',          momentum_score: 0.5, vol_level: 'high'});
MERGE (:Regime {name: 'LowVolatility',   description: 'Compressed vol, range-bound, carry-favourable',      momentum_score: 0.3, vol_level: 'low'});
MERGE (:Regime {name: 'Crisis',          description: 'Fat tails, correlation spike, liquidity stress',     momentum_score: 0.1, vol_level: 'extreme'});
MERGE (:Regime {name: 'SystemicStress',  description: 'Densifying interbank network, rising contagion probability, shadow banking expansion, pre-crisis liquidity pressure', momentum_score: 0.15, vol_level: 'extreme'});
MERGE (:Regime {name: 'Recovery',        description: 'Post-crisis mean-reversion with rising vol of vol',  momentum_score: 0.6, vol_level: 'medium'});
MERGE (:Regime {name: 'Neutral',         description: 'Default baseline, no strong directional or vol signal', momentum_score: 0.5, vol_level: 'medium'});


// -----------------------------------------------------------------------------
// 3. CONCEPT NODES  (seeded from concepts.cypher CSV)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Black-Scholes Model'})
  SET c.definition   = 'Continuous-time option pricing framework assuming GBM dynamics and constant volatility. Core equation: C = S·N(d₁) - K·e^(-rτ)·N(d₂)',
      c.category     = 'option_pricing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'European Call Option'})
  SET c.definition   = 'Financial contract giving holder the right to buy underlying at strike K at maturity T. Payoff: max(S_T - K, 0)',
      c.category     = 'derivatives',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'European Put Option'})
  SET c.definition   = 'Financial contract giving holder the right to sell underlying at strike K at maturity T. Payoff: max(K - S_T, 0)',
      c.category     = 'derivatives',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Heston Model'})
  SET c.definition   = 'Stochastic volatility model: dS=rS·dt+√v·S·dW₁, dv=κ(θ-v)·dt+ξ√v·dW₂ with correlation ρ. Captures volatility smile.',
      c.category     = 'option_pricing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Volatility Smile'})
  SET c.definition   = 'Pattern where implied volatility varies with strike and maturity; contradicts BS constant volatility assumption',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Implied Volatility'})
  SET c.definition   = 'Volatility parameter σ that equates model price to market price. Market expectation of future volatility.',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Greeks'})
  SET c.definition   = 'Partial derivatives of option price: Δ=∂V/∂S, Γ=∂²V/∂S², Θ=∂V/∂t, ν=∂V/∂σ, ρ=∂V/∂r',
      c.category     = 'risk_management',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Delta Hedging'})
  SET c.definition   = 'Maintaining delta-neutral position by holding -Δ shares per short option. Eliminates first-order price risk.',
      c.category     = 'hedging',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Gamma Scalping'})
  SET c.definition   = 'Profiting from gamma by dynamically delta-hedging. Long gamma benefits from large price moves.',
      c.category     = 'trading_strategy',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Put-Call Parity'})
  SET c.definition   = 'No-arbitrage relationship: C - P = S - K·e^(-rτ). Enables put pricing from call price.',
      c.category     = 'arbitrage',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Risk-Neutral Pricing'})
  SET c.definition   = 'Valuation framework where discounted asset prices are martingales under equivalent measure Q.',
      c.category     = 'measure_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Geometric Brownian Motion'})
  SET c.definition   = 'Stochastic process dS = μS·dt + σS·dW modeling asset prices with constant drift and volatility.',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Monte Carlo Pricing'})
  SET c.definition   = 'Numerical method using random sampling: C = e^(-rT)·E^Q[max(S_T-K,0)]. Converges as O(1/√N).',
      c.category     = 'numerical_methods',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'FFT Pricing'})
  SET c.definition   = 'Option pricing via Fast Fourier Transform of characteristic function. O(N·logN) complexity.',
      c.category     = 'numerical_methods',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Characteristic Function'})
  SET c.definition   = 'Fourier transform φ(u)=E[e^(iuX)] of probability distribution. Enables analytic pricing for affine models.',
      c.category     = 'mathematical_finance',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'CIR Process'})
  SET c.definition   = 'Square-root diffusion: dv=κ(θ-v)dt+ξ√v·dW. Ensures non-negative variance. Feller condition: 2κθ>ξ².',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Feller Condition'})
  SET c.definition   = 'Condition 2κθ > ξ² ensuring CIR process stays strictly positive (never hits zero).',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Time Decay (Theta)'})
  SET c.definition   = 'Daily loss in option value as expiration approaches. Θ = ∂V/∂t. Negative for long options.',
      c.category     = 'greeks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Vega Risk'})
  SET c.definition   = 'Sensitivity to implied volatility changes. ν = ∂V/∂σ. Same for calls and puts.',
      c.category     = 'greeks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Local Volatility'})
  SET c.definition   = 'Deterministic volatility function σ(S,t) calibrated to match vanilla prices. Dupire formula.',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'SABR Model'})
  SET c.definition   = 'Stochastic-alpha-beta-rho: dα=ν·α·dW₁, df=α·f^β·dW₂. Popular asymptotic formula for volatility smile.',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Variance Gamma'})
  SET c.definition   = 'Lévy process with gamma time change. Captures fat tails and skewness in returns.',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Jump Diffusion'})
  SET c.definition   = 'Model with continuous diffusion plus Poisson jumps: dS/S = (μ-λκ)dt + σdW + dJ.',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Barrier Option'})
  SET c.definition   = 'Exotic option that activates/knocks out when underlying hits barrier level.',
      c.category     = 'exotic_derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Asian Option'})
  SET c.definition   = 'Exotic option with payoff based on average price of underlying over period.',
      c.category     = 'exotic_derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Lookback Option'})
  SET c.definition   = 'Exotic option with payoff based on maximum/minimum price over life of option.',
      c.category     = 'exotic_derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Binary Option'})
  SET c.definition   = 'Option with fixed payoff if condition met (e.g., S_T > K). Also called digital option.',
      c.category     = 'exotic_derivatives',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Forward Contract'})
  SET c.definition   = 'Agreement to buy/sell asset at future date T for price K set today. Value: S - K·e^(-rτ).',
      c.category     = 'derivatives',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer';

MERGE (c:Concept {name: 'Swap Contract'})
  SET c.definition   = 'Agreement to exchange cash flows (e.g., fixed vs floating rate). Value = PV(floating) - PV(fixed).',
      c.category     = 'derivatives',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer';


// -----------------------------------------------------------------------------
// 4. CONCEPT → CATEGORY RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (c:Concept), (cat:Category) WHERE c.category = cat.name
MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// 5. PREREQUISITE RELATIONSHIPS  (from CSV prerequisites column)
// -----------------------------------------------------------------------------

// Black-Scholes prerequisites
MATCH (a:Concept {name:'Geometric Brownian Motion'}), (b:Concept {name:'Black-Scholes Model'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Risk-Neutral Pricing'}),      (b:Concept {name:'Black-Scholes Model'})   MERGE (a)-[:PREREQ_OF]->(b);

// Heston prerequisites
MATCH (a:Concept {name:'Implied Volatility'}),        (b:Concept {name:'Heston Model'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CIR Process'}),               (b:Concept {name:'Heston Model'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Characteristic Function'}),   (b:Concept {name:'Heston Model'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Feller Condition'}),          (b:Concept {name:'Heston Model'})          MERGE (a)-[:PREREQ_OF]->(b);

// Greeks prerequisites
MATCH (a:Concept {name:'Black-Scholes Model'}),       (b:Concept {name:'Greeks'})                MERGE (a)-[:PREREQ_OF]->(b);

// Delta Hedging prerequisites
MATCH (a:Concept {name:'Greeks'}),                    (b:Concept {name:'Delta Hedging'})         MERGE (a)-[:PREREQ_OF]->(b);

// Gamma Scalping prerequisites
MATCH (a:Concept {name:'Delta Hedging'}),             (b:Concept {name:'Gamma Scalping'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Greeks'}),                    (b:Concept {name:'Gamma Scalping'})        MERGE (a)-[:PREREQ_OF]->(b);

// Put-Call Parity prerequisites
MATCH (a:Concept {name:'Forward Contract'}),          (b:Concept {name:'Put-Call Parity'})       MERGE (a)-[:PREREQ_OF]->(b);

// Risk-Neutral Pricing prerequisites
MATCH (a:Concept {name:'Geometric Brownian Motion'}), (b:Concept {name:'Risk-Neutral Pricing'}) MERGE (a)-[:PREREQ_OF]->(b);

// FFT Pricing prerequisites
MATCH (a:Concept {name:'Characteristic Function'}),   (b:Concept {name:'FFT Pricing'})           MERGE (a)-[:PREREQ_OF]->(b);

// CIR Process prerequisites
MATCH (a:Concept {name:'Feller Condition'}),          (b:Concept {name:'CIR Process'})           MERGE (a)-[:PREREQ_OF]->(b);

// Local Volatility prerequisites
MATCH (a:Concept {name:'Implied Volatility'}),        (b:Concept {name:'Local Volatility'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Volatility Smile'}),          (b:Concept {name:'Local Volatility'})      MERGE (a)-[:PREREQ_OF]->(b);

// SABR prerequisites
MATCH (a:Concept {name:'Volatility Smile'}),          (b:Concept {name:'SABR Model'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implied Volatility'}),        (b:Concept {name:'SABR Model'})            MERGE (a)-[:PREREQ_OF]->(b);

// Monte Carlo prerequisites
MATCH (a:Concept {name:'Geometric Brownian Motion'}), (b:Concept {name:'Monte Carlo Pricing'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Risk-Neutral Pricing'}),      (b:Concept {name:'Monte Carlo Pricing'})  MERGE (a)-[:PREREQ_OF]->(b);

// Jump Diffusion prerequisites
MATCH (a:Concept {name:'Geometric Brownian Motion'}), (b:Concept {name:'Jump Diffusion'})       MERGE (a)-[:PREREQ_OF]->(b);

// Variance Gamma prerequisites
MATCH (a:Concept {name:'Jump Diffusion'}),            (b:Concept {name:'Variance Gamma'})       MERGE (a)-[:PREREQ_OF]->(b);

// Exotics prerequisites
MATCH (a:Concept {name:'Monte Carlo Pricing'}),       (b:Concept {name:'Barrier Option'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Monte Carlo Pricing'}),       (b:Concept {name:'Asian Option'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Monte Carlo Pricing'}),       (b:Concept {name:'Lookback Option'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Risk-Neutral Pricing'}),      (b:Concept {name:'Binary Option'})        MERGE (a)-[:PREREQ_OF]->(b);

// Time Decay / Vega prerequisites
MATCH (a:Concept {name:'Greeks'}),                    (b:Concept {name:'Time Decay (Theta)'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Greeks'}),                    (b:Concept {name:'Vega Risk'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implied Volatility'}),        (b:Concept {name:'Vega Risk'})             MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// 6. FORMULA NODES  (mathematical expressions keyed to concepts)
// -----------------------------------------------------------------------------
MERGE (f:Formula {id: 'f_bs_call'})
  SET f.name       = 'Black-Scholes Call Price',
      f.expression = 'C = S·N(d₁) - K·e^{-rτ}·N(d₂)',
      f.`latex`     = 'C = S \\cdot \\Phi(d_1) - K e^{-r\\tau} \\cdot \\Phi(d_2)',
      f.params      = ['S','K','r','τ','σ'],
      f.output      = 'call_price';

MERGE (f:Formula {id: 'f_bs_d1'})
  SET f.name       = 'BS d₁ component',
      f.expression = 'd₁ = [ln(S/K) + (r + σ²/2)τ] / (σ√τ)',
      f.`latex`     = 'd_1 = \\frac{\\ln(S/K)+(r+\\sigma^2/2)\\tau}{\\sigma\\sqrt{\\tau}}',
      f.params      = ['S','K','r','τ','σ'],
      f.output      = 'd1';

MERGE (f:Formula {id: 'f_bs_d2'})
  SET f.name       = 'BS d₂ component',
      f.expression = 'd₂ = d₁ - σ√τ',
      f.`latex`     = 'd_2 = d_1 - \\sigma\\sqrt{\\tau}',
      f.params      = ['d1','σ','τ'],
      f.output      = 'd2';

MERGE (f:Formula {id: 'f_delta'})
  SET f.name       = 'Delta (call)',
      f.expression = 'Δ = N(d₁)',
      f.`latex`     = '\\Delta = \\Phi(d_1)',
      f.params      = ['d1'],
      f.output      = 'delta';

MERGE (f:Formula {id: 'f_gamma'})
  SET f.name       = 'Gamma',
      f.expression = 'Γ = N′(d₁) / (S·σ·√τ)',
      f.`latex`     = '\\Gamma = \\frac{\\phi(d_1)}{S \\sigma \\sqrt{\\tau}}',
      f.params      = ['d1','S','σ','τ'],
      f.output      = 'gamma';

MERGE (f:Formula {id: 'f_theta'})
  SET f.name       = 'Theta (call)',
      f.expression = 'Θ = -S·N′(d₁)·σ/(2√τ) - r·K·e^(-rτ)·N(d₂)',
      f.`latex`     = '\\Theta = -\\frac{S\\phi(d_1)\\sigma}{2\\sqrt{\\tau}} - rKe^{-r\\tau}\\Phi(d_2)',
      f.params      = ['S','K','r','τ','σ','d1','d2'],
      f.output      = 'theta';

MERGE (f:Formula {id: 'f_vega'})
  SET f.name       = 'Vega',
      f.expression = 'ν = S·N′(d₁)·√τ',
      f.`latex`     = '\\nu = S \\phi(d_1) \\sqrt{\\tau}',
      f.params      = ['S','d1','τ'],
      f.output      = 'vega';

MERGE (f:Formula {id: 'f_pcp'})
  SET f.name       = 'Put-Call Parity',
      f.expression = 'C - P = S - K·e^(-rτ)',
      f.`latex`     = 'C - P = S - Ke^{-r\\tau}',
      f.params      = ['C','P','S','K','r','τ'],
      f.output      = 'parity_check';

MERGE (f:Formula {id: 'f_gbm'})
  SET f.name       = 'GBM SDE',
      f.expression = 'dS = μS·dt + σS·dW',
      f.`latex`     = 'dS = \\mu S\\,dt + \\sigma S\\,dW_t',
      f.params      = ['S','μ','σ'],
      f.output      = 'dS';

MERGE (f:Formula {id: 'f_heston_s'})
  SET f.name       = 'Heston price SDE',
      f.expression = 'dS = rS·dt + √v·S·dW₁',
      f.`latex`     = 'dS = rS\\,dt + \\sqrt{v}\\,S\\,dW_1',
      f.params      = ['S','r','v'],
      f.output      = 'dS';

MERGE (f:Formula {id: 'f_heston_v'})
  SET f.name       = 'Heston variance SDE',
      f.expression = 'dv = κ(θ-v)·dt + ξ√v·dW₂',
      f.`latex`     = 'dv = \\kappa(\\theta-v)\\,dt + \\xi\\sqrt{v}\\,dW_2',
      f.params      = ['v','κ','θ','ξ'],
      f.output      = 'dv';

MERGE (f:Formula {id: 'f_cir'})
  SET f.name       = 'CIR Process',
      f.expression = 'dv = κ(θ-v)·dt + ξ√v·dW',
      f.`latex`     = 'dv = \\kappa(\\theta - v)\\,dt + \\xi\\sqrt{v}\\,dW',
      f.params      = ['v','κ','θ','ξ'],
      f.output      = 'dv';

MERGE (f:Formula {id: 'f_feller'})
  SET f.name       = 'Feller Condition',
      f.expression = '2κθ > ξ²',
      f.`latex`     = '2\\kappa\\theta > \\xi^2',
      f.params      = ['κ','θ','ξ'],
      f.output      = 'boolean';

MERGE (f:Formula {id: 'f_mc'})
  SET f.name       = 'Monte Carlo estimator',
      f.expression = 'C ≈ e^(-rT) · (1/N) · Σ max(S_T^i - K, 0)',
      f.`latex`     = 'C \\approx e^{-rT}\\frac{1}{N}\\sum_{i=1}^N\\max(S_T^i-K,0)',
      f.params      = ['r','T','K','N'],
      f.output      = 'price_estimate';

MERGE (f:Formula {id: 'f_roc'})
  SET f.name       = 'Rate of Change (momentum)',
      f.expression = 'ROC(n) = (P_t - P_{t-n}) / P_{t-n} × 100',
      f.`latex`     = 'ROC_n = \\frac{P_t - P_{t-n}}{P_{t-n}} \\times 100',
      f.params      = ['P_t','P_tn','n'],
      f.output      = 'momentum_score';

MERGE (f:Formula {id: 'f_zscore'})
  SET f.name       = 'Z-score (mean reversion)',
      f.expression = 'z = (x - μ) / σ',
      f.`latex`     = 'z = \\frac{x - \\mu}{\\sigma}',
      f.params      = ['x','μ','σ'],
      f.output      = 'z_score';

MERGE (f:Formula {id: 'f_kelly'})
  SET f.name       = 'Kelly Criterion',
      f.expression = 'f* = (bp - q) / b  where b=odds, p=win_prob, q=1-p',
      f.`latex`     = 'f^* = \\frac{bp - q}{b}',
      f.params      = ['b','p','q'],
      f.output      = 'position_fraction';

MERGE (f:Formula {id: 'f_sharpe'})
  SET f.name       = 'Sharpe Ratio',
      f.expression = 'SR = (R_p - R_f) / σ_p',
      f.`latex`     = 'SR = \\frac{R_p - R_f}{\\sigma_p}',
      f.params      = ['R_p','R_f','σ_p'],
      f.output      = 'risk_adjusted_return';
// -----------------------------------------------------------------------------
// 7. CONCEPT → FORMULA RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Black-Scholes Model'}), (f:Formula {id:'f_bs_call'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Black-Scholes Model'}), (f:Formula {id:'f_bs_d1'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Black-Scholes Model'}), (f:Formula {id:'f_bs_d2'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Greeks'}),               (f:Formula {id:'f_delta'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Greeks'}),               (f:Formula {id:'f_gamma'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Greeks'}),               (f:Formula {id:'f_vega'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Time Decay (Theta)'}),   (f:Formula {id:'f_theta'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Vega Risk'}),            (f:Formula {id:'f_vega'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Put-Call Parity'}),      (f:Formula {id:'f_pcp'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Geometric Brownian Motion'}),(f:Formula {id:'f_gbm'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Heston Model'}),         (f:Formula {id:'f_heston_s'})MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Heston Model'}),         (f:Formula {id:'f_heston_v'})MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'CIR Process'}),          (f:Formula {id:'f_cir'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Feller Condition'}),     (f:Formula {id:'f_feller'})  MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Monte Carlo Pricing'}),  (f:Formula {id:'f_mc'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Gamma Scalping'}),       (f:Formula {id:'f_roc'})     MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 8. STRATEGY NODES  (instantiated from tradeable concepts)
// These are runtime nodes the agent activates — derived from Concept nodes
// but enriched with execution parameters.
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'Momentum Breakout'})
  SET s.derived_from       = 'Gamma Scalping',
      s.description        = 'Enter long when ROC(14) crosses threshold; size via Kelly',
      s.formula_ref        = 'f_roc',
      s.sizing_formula_ref = 'f_kelly',
      s.param_lookback     = 14,
      s.param_threshold    = 2.0,
      s.risk_weight        = 0.6,
      s.status             = 'active',
      s.target_ticker      = 'QQQ';

MERGE (s:Strategy {name: 'Volatility Mean Reversion'})
  SET s.derived_from       = 'Implied Volatility',
      s.description        = 'Short vol when IV z-score > 2; hedge with delta',
      s.formula_ref        = 'f_zscore',
      s.sizing_formula_ref = 'f_kelly',
      s.param_zscore_entry = 2.0,
      s.param_zscore_exit  = 0.5,
      s.risk_weight        = 0.5,
      s.status             = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Delta-Neutral Carry'})
  SET s.derived_from       = 'Delta Hedging',
      s.description        = 'Hold delta-neutral portfolio and harvest theta decay',
      s.formula_ref        = 'f_theta',
      s.sizing_formula_ref = 'f_sharpe',
      s.param_rebalance_h  = 4,
      s.risk_weight        = 0.4,
      s.status             = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Gamma Scalp'})
  SET s.derived_from       = 'Gamma Scalping',
      s.description        = 'Long gamma via straddles; delta hedge continuously',
      s.formula_ref        = 'f_gamma',
      s.sizing_formula_ref = 'f_kelly',
      s.param_gamma_min    = 0.05,
      s.risk_weight        = 0.7,
      s.status             = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Vol Surface Arb'})
  SET s.derived_from       = 'Volatility Smile',
      s.description        = 'Exploit violations in put-call parity across strikes',
      s.formula_ref        = 'f_pcp',
      s.sizing_formula_ref = 'f_sharpe',
      s.param_arb_threshold= 0.005,
      s.risk_weight        = 0.3,
      s.status             = 'active',
      s.target_ticker      = 'QQQ';


// -----------------------------------------------------------------------------
// 9. STRATEGY → CONCEPT (derived from) RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Momentum Breakout'}),       (c:Concept {name:'Gamma Scalping'})     MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Volatility Mean Reversion'}),(c:Concept {name:'Implied Volatility'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Delta-Neutral Carry'}),      (c:Concept {name:'Delta Hedging'})      MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Gamma Scalp'}),              (c:Concept {name:'Gamma Scalping'})     MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Vol Surface Arb'}),          (c:Concept {name:'Volatility Smile'})   MERGE (s)-[:DERIVED_FROM]->(c);


// -----------------------------------------------------------------------------
// 10. STRATEGY → FORMULA RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Momentum Breakout'}),       (f:Formula {id:'f_roc'})    MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Momentum Breakout'}),       (f:Formula {id:'f_kelly'})  MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Volatility Mean Reversion'}),(f:Formula {id:'f_zscore'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Delta-Neutral Carry'}),      (f:Formula {id:'f_theta'})  MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Delta-Neutral Carry'}),      (f:Formula {id:'f_sharpe'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Gamma Scalp'}),              (f:Formula {id:'f_gamma'})  MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Vol Surface Arb'}),          (f:Formula {id:'f_pcp'})    MERGE (s)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 11. STRATEGY → REGIME (ACTIVATED_BY) RELATIONSHIPS
// These govern which strategies the agent considers in each detected regime
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Momentum Breakout'}),        (r:Regime {name:'Trending'})       MERGE (s)-[:ACTIVATED_BY {weight:0.9}]->(r);
MATCH (s:Strategy {name:'Momentum Breakout'}),        (r:Regime {name:'Recovery'})       MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name:'Volatility Mean Reversion'}),(r:Regime {name:'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Volatility Mean Reversion'}),(r:Regime {name:'MeanReverting'})  MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name:'Delta-Neutral Carry'}),      (r:Regime {name:'LowVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.8}]->(r);
MATCH (s:Strategy {name:'Delta-Neutral Carry'}),      (r:Regime {name:'MeanReverting'})  MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name:'Gamma Scalp'}),              (r:Regime {name:'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.9}]->(r);
MATCH (s:Strategy {name:'Gamma Scalp'}),              (r:Regime {name:'Crisis'})         MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name:'Vol Surface Arb'}),          (r:Regime {name:'LowVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.75}]->(r);
MATCH (s:Strategy {name:'Vol Surface Arb'}),          (r:Regime {name:'MeanReverting'})  MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);


// -----------------------------------------------------------------------------
// 12. STRATEGY → STRATEGY (CONTRADICTED_BY) RELATIONSHIPS
// Agent uses these to avoid conflicting simultaneous positions
// -----------------------------------------------------------------------------

MATCH (a:Strategy {name:'Momentum Breakout'}),       (b:Strategy {name:'Volatility Mean Reversion'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name:'Delta-Neutral Carry'}),      (b:Strategy {name:'Gamma Scalp'})              MERGE (a)-[:CONTRADICTED_BY]->(b);


// -----------------------------------------------------------------------------
// 13. XSTOCK TICKER NODES (initial xStocks universe)
// Augment when Kraken xStocks list is confirmed
// -----------------------------------------------------------------------------

MERGE (:Ticker {symbol:'AAPL',  name:'Apple Inc.',          sector:'Technology',    asset_class:'xStock'});
MERGE (:Ticker {symbol:'MSFT',  name:'Microsoft Corp.',     sector:'Technology',    asset_class:'xStock'});
MERGE (:Ticker {symbol:'NVDA',  name:'NVIDIA Corp.',        sector:'Technology',    asset_class:'xStock'});
MERGE (:Ticker {symbol:'TSLA',  name:'Tesla Inc.',          sector:'Consumer',      asset_class:'xStock'});
MERGE (:Ticker {symbol:'SPY',   name:'S&P 500 ETF',         sector:'Broad Market',  asset_class:'xETF'});
MERGE (:Ticker {symbol:'QQQ',   name:'Nasdaq 100 ETF',      sector:'Technology',    asset_class:'xETF'});
MERGE (:Ticker {symbol:'GLD',   name:'Gold ETF',            sector:'Commodities',   asset_class:'xETF'});
MERGE (:Ticker {symbol:'JPM',   name:'JPMorgan Chase',      sector:'Financials',    asset_class:'xStock'});
MERGE (:Ticker {symbol:'AMZN',  name:'Amazon.com Inc.',     sector:'Consumer',      asset_class:'xStock'});
MERGE (:Ticker {symbol:'GOOGL', name:'Alphabet Inc.',       sector:'Technology',    asset_class:'xStock'});


// -----------------------------------------------------------------------------
// 14. RUNTIME SIGNAL TEMPLATE (empty — agent populates at runtime)
// Agent creates Signal nodes via:
//   CREATE (sig:Signal {
//     id: uuid(),
//     strategy_name: '...',
//     ticker: '...',
//     direction: 'LONG'|'SHORT',
//     strength: 0.0-1.0,
//     formula_used: 'f_roc',
//     param_values: '{"n":14,"P_t":182.5,"P_tn":175.0}',
//     regime_at_signal: 'Trending',
//     created_at: timestamp(),
//     status: 'PENDING'|'EXECUTED'|'EXPIRED'
//   })
// Then links: (Strategy)-[:HAS_SIGNAL]->(sig)-[:TARGETS]->(Ticker)
// =============================================================================


// -----------------------------------------------------------------------------
// 15. USEFUL AGENT QUERY PATTERNS
// (stored as comments — copy into agent query modules)
// -----------------------------------------------------------------------------

// Q1: Which strategies are active for a detected regime?
// MATCH (s:Strategy)-[r:ACTIVATED_BY]->(reg:Regime {name: $regime})
// WHERE s.status = 'active'
// RETURN s, r.weight ORDER BY r.weight DESC

// Q2: Full reasoning trace for a strategy
// MATCH path = (s:Strategy {name: $strategy_name})-[:DERIVED_FROM]->(c:Concept)-[:HAS_FORMULA]->(f:Formula)
// RETURN path

// Q3: Contradictions check before opening position
// MATCH (open:Strategy)-[:HAS_SIGNAL]->(sig:Signal {status:'EXECUTED'}),
//       (open)-[:CONTRADICTED_BY]->(target:Strategy {name: $candidate})
// RETURN open.name AS blocking_strategy

// Q4: Signal strength leaderboard
// MATCH (s:Strategy)-[:HAS_SIGNAL]->(sig:Signal {status:'PENDING'})-[:TARGETS]->(t:Ticker)
// RETURN s.name, t.symbol, sig.strength, sig.direction
// ORDER BY sig.strength DESC LIMIT 10

// Q5: Prerequisite chain depth for a concept
// MATCH path = (root:Concept)-[:PREREQ_OF*]->(c:Concept {name: $concept_name})
// RETURN path, length(path) AS depth ORDER BY depth DESC

// Q6: Factor model concepts active in current regime
// MATCH (s:Strategy)-[:ACTIVATED_BY]->(r:Regime {name: $regime}),
//       (s)-[:DERIVED_FROM]->(c:Concept)-[:BELONGS_TO]->(cat:Category {name:'factor_investing'})
// RETURN s.name, c.name, r.name ORDER BY s.risk_weight DESC

// Q7: Cross-category concept bridge (options ↔ factor)
// MATCH (a:Concept)-[:PREREQ_OF*1..3]->(b:Concept)
// WHERE a.category <> b.category
// RETURN a.name, a.category, b.name, b.category LIMIT 20


// =============================================================================
// v0.2.0 ADDITIONS — FACTOR INVESTING, ASSET PRICING, RISK & ESTIMATION
// =============================================================================


// -----------------------------------------------------------------------------
// 16. CONCEPT NODES — FACTOR INVESTING & ASSET PRICING BATCH
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Factor Model'})
  SET c.definition   = 'Asset returns driven by common factors: R_it = α_i + βᵢᵀ·f_t + ε_it. Explains cross-section of returns.',
      c.category     = 'asset_pricing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Loading (Beta)'})
  SET c.definition   = 'β_ik = Cov(R_i,f_k)/Var(f_k). Sensitivity of asset i to factor k. Regression coefficient.',
      c.category     = 'factor_investing',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Alpha (Factor)'})
  SET c.definition   = 'α_i = E[R_i] - βᵢᵀ·E[f]. Abnormal return unexplained by factors. Skill or mispricing.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Return'})
  SET c.definition   = 'f_kt. Return to factor k at time t. Can be traded via long-short portfolio.',
      c.category     = 'factor_investing',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Idiosyncratic Return'})
  SET c.definition   = 'ε_it. Asset-specific return unexplained by factors. E[ε_it]=0, uncorrelated across assets.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'R-Squared'})
  SET c.definition   = 'R² = 1 - Var(ε)/Var(R). Fraction of return variance explained by factors.',
      c.category     = 'statistics',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Fama-French 3-Factor'})
  SET c.definition   = 'Model with MKT (market), SMB (size), HML (value). R_it = α + β_mkt·MKT + β_smb·SMB + β_hml·HML + ε.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Fama-French 5-Factor'})
  SET c.definition   = 'Extends 3-factor with RMW (profitability) and CMA (investment).',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Carhart 4-Factor'})
  SET c.definition   = 'Fama-French 3-factor + MOM (momentum). Captures momentum anomaly.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'q-Factor Model'})
  SET c.definition   = 'Hou-Xue-Zhang: Market, Size, Investment, Profitability factors. Based on q-theory of investment.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'CAPM'})
  SET c.definition   = 'Capital Asset Pricing Model: E[R_i] = r_f + β_i·(E[R_m] - r_f). Single-factor model.',
      c.category     = 'asset_pricing',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'APT'})
  SET c.definition   = 'Arbitrage Pricing Theory: E[R_i] = r_f + Σ_k β_ik·λ_k. Multi-factor generalization of CAPM.',
      c.category     = 'asset_pricing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'PCA Factors'})
  SET c.definition   = 'Principal Component Analysis factors. Eigenvectors of covariance matrix explaining maximum variance.',
      c.category     = 'dimensionality_reduction',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Statistical Factors'})
  SET c.definition   = 'Factors extracted via statistical methods (PCA, factor analysis). No direct economic interpretation.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Macroeconomic Factors'})
  SET c.definition   = 'Factors based on macro variables: GDP growth, inflation, interest rates, credit spread.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Style Factors'})
  SET c.definition   = 'Factors based on stock characteristics: value, size, momentum, quality, low volatility.',
      c.category     = 'factor_investing',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Industry Factors'})
  SET c.definition   = 'Sector/industry classification factors. Orthogonalized to style factors.',
      c.category     = 'factor_investing',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Smart Beta'})
  SET c.definition   = 'Rules-based strategies targeting specific factors. Alternative to market-cap weighting.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Momentum'})
  SET c.definition   = 'Persistence in factor returns. Winner factors continue winning, loser factors continue losing.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Rotation'})
  SET c.definition   = 'Adjusting factor exposure based on market conditions or forward-looking signals.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Timing'})
  SET c.definition   = 'Predicting factor returns and adjusting exposure dynamically. Controversial efficacy.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Value Premium'})
  SET c.definition   = 'HML (High Minus Low): Long value stocks (high B/M), short growth stocks (low B/M).',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Size Premium'})
  SET c.definition   = 'SMB (Small Minus Big): Long small-cap stocks, short large-cap stocks.',
      c.category     = 'factor_investing',
      c.difficulty   = 'basic',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Momentum Premium'})
  SET c.definition   = 'MOM: Long past winners (12-1 month returns), short past losers.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Quality Premium'})
  SET c.definition   = 'Profitability factor: Long high-quality (profitable) stocks, short low-quality stocks.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Low Volatility Anomaly'})
  SET c.definition   = 'Low beta/volatility stocks outperform high beta/volatility on risk-adjusted basis.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Crowding'})
  SET c.definition   = 'Multiple investors holding similar factor exposures. Increases correlation and crash risk.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Capacity'})
  SET c.definition   = 'Maximum AUM before factor returns degrade. Limited by liquidity and arbitrage costs.',
      c.category     = 'factor_investing',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Covariance Shrinkage'})
  SET c.definition   = 'Σ̂_shrink = (1-λ)Σ̂_sample + λ·F. Improves estimation by shrinking toward structured target.',
      c.category     = 'estimation',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Ledoit-Wolf Shrinkage'})
  SET c.definition   = 'Optimal shrinkage intensity λ* minimizing MSE. F = constant correlation or single-index target.',
      c.category     = 'estimation',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Covariance'})
  SET c.definition   = 'Σ_f = Cov(f_t). Covariance matrix of factor returns. Used for risk attribution.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Specific Risk'})
  SET c.definition   = 'Var(ε_i). Asset-specific variance unexplained by factors. Also called idiosyncratic risk.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Fundamental Factor Model'})
  SET c.definition   = 'Factors based on fundamental data: earnings, book value, dividends.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Risk Model'})
  SET c.definition   = 'Model of return covariance: Σ = B·Σ_f·Bᵀ + D. B=loadings matrix, D=specific risk diagonal.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'advanced',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Factor Attribution'})
  SET c.definition   = 'Decomposing portfolio return into factor exposures and selection: R_p = Σ_k β_pk·f_k + α.',
      c.category     = 'performance_attribution',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';

MERGE (c:Concept {name: 'Active Factor Exposure'})
  SET c.definition   = 'β_p,k - β_benchmark,k. Portfolio factor tilt relative to benchmark.',
      c.category     = 'factor_investing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Factor';


// -----------------------------------------------------------------------------
// 17. NEW CONCEPT → CATEGORY RELATIONSHIPS (v0.2.0 batch)
// Run after all new Concept nodes are merged
// -----------------------------------------------------------------------------

MATCH (c:Concept), (cat:Category)
WHERE c.category = cat.name
  AND c.menu_context = 'Factor'
MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// 18. PREREQUISITE RELATIONSHIPS — FACTOR BATCH
// -----------------------------------------------------------------------------

// CAPM is the foundation for most factor models
MATCH (a:Concept {name:'CAPM'}),              (b:Concept {name:'Factor Model'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CAPM'}),              (b:Concept {name:'APT'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CAPM'}),              (b:Concept {name:'Fama-French 3-Factor'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CAPM'}),              (b:Concept {name:'Low Volatility Anomaly'}) MERGE (a)-[:PREREQ_OF]->(b);

// Factor Model → its sub-components
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Factor Loading (Beta)'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Alpha (Factor)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Factor Return'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Idiosyncratic Return'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'R-Squared'})              MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Risk Model'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Factor Attribution'})     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Model'}),      (b:Concept {name:'Factor Covariance'})      MERGE (a)-[:PREREQ_OF]->(b);

// Fama-French family
MATCH (a:Concept {name:'Fama-French 3-Factor'}),(b:Concept {name:'Fama-French 5-Factor'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fama-French 3-Factor'}),(b:Concept {name:'Carhart 4-Factor'})     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fama-French 5-Factor'}),(b:Concept {name:'q-Factor Model'})       MERGE (a)-[:PREREQ_OF]->(b);

// Style/premium prerequisites
MATCH (a:Concept {name:'Value Premium'}),     (b:Concept {name:'Fama-French 3-Factor'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Size Premium'}),      (b:Concept {name:'Fama-French 3-Factor'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Momentum Premium'}),  (b:Concept {name:'Carhart 4-Factor'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Quality Premium'}),   (b:Concept {name:'Fama-French 5-Factor'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Style Factors'}),     (b:Concept {name:'Smart Beta'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Style Factors'}),     (b:Concept {name:'Factor Rotation'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Style Factors'}),     (b:Concept {name:'Factor Timing'})          MERGE (a)-[:PREREQ_OF]->(b);

// Factor dynamics
MATCH (a:Concept {name:'Factor Return'}),     (b:Concept {name:'Factor Momentum'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Rotation'}),   (b:Concept {name:'Factor Timing'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowding'}),          (b:Concept {name:'Factor Capacity'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Loading (Beta)'}),(b:Concept {name:'Active Factor Exposure'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Attribution'}),(b:Concept {name:'Active Factor Exposure'})  MERGE (a)-[:PREREQ_OF]->(b);

// Estimation prerequisites
MATCH (a:Concept {name:'Covariance Shrinkage'}),(b:Concept {name:'Ledoit-Wolf Shrinkage'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Covariance Shrinkage'}),(b:Concept {name:'Risk Model'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Covariance'}),  (b:Concept {name:'Risk Model'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Specific Risk'}),      (b:Concept {name:'Risk Model'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Idiosyncratic Return'}),(b:Concept {name:'Specific Risk'})         MERGE (a)-[:PREREQ_OF]->(b);

// PCA → Statistical Factors
MATCH (a:Concept {name:'PCA Factors'}),        (b:Concept {name:'Statistical Factors'})    MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain bridge: options ↔ factor (vol as a factor)
MATCH (a:Concept {name:'Implied Volatility'}), (b:Concept {name:'Low Volatility Anomaly'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Greeks'}),             (b:Concept {name:'Factor Loading (Beta)'})  MERGE (a)-[:PREREQ_OF]->(b);

// Macro factors
MATCH (a:Concept {name:'Macroeconomic Factors'}),(b:Concept {name:'Factor Rotation'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Macroeconomic Factors'}),(b:Concept {name:'Factor Timing'})        MERGE (a)-[:PREREQ_OF]->(b);

// Fundamental
MATCH (a:Concept {name:'Fundamental Factor Model'}),(b:Concept {name:'Value Premium'})     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fundamental Factor Model'}),(b:Concept {name:'Quality Premium'})   MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// 19. FORMULA NODES — FACTOR BATCH
// -----------------------------------------------------------------------------
MERGE (f:Formula {id: 'f_factor_model'})
  SET f.name       = 'Factor Model Return Decomposition',
      f.expression = 'R_it = α_i + βᵢᵀ·f_t + ε_it',
      f.`latex`     = 'R_{it} = \\alpha_i + \\boldsymbol{\\beta}_i^\\top \\mathbf{f}_t + \\varepsilon_{it}',
      f.params      = ['α_i','β_i','f_t'],
      f.output      = 'asset_return';

MERGE (f:Formula {id: 'f_capm'})
  SET f.name       = 'CAPM Expected Return',
      f.expression = 'E[R_i] = r_f + β_i·(E[R_m] - r_f)',
      f.`latex`     = 'E[R_i] = r_f + \\beta_i (E[R_m] - r_f)',
      f.params      = ['r_f','β_i','E_Rm'],
      f.output      = 'expected_return';

MERGE (f:Formula {id: 'f_apt'})
  SET f.name       = 'APT Expected Return',
      f.expression = 'E[R_i] = r_f + Σ_k β_ik·λ_k',
      f.`latex`     = 'E[R_i] = r_f + \\sum_k \\beta_{ik} \\lambda_k',
      f.params      = ['r_f','β_ik','λ_k'],
      f.output      = 'expected_return';

MERGE (f:Formula {id: 'f_risk_model'})
  SET f.name       = 'Structural Risk Model',
      f.expression = 'Σ = B·Σ_f·Bᵀ + D',
      f.`latex`     = '\\Sigma = \\mathbf{B}\\Sigma_f\\mathbf{B}^\\top + \\mathbf{D}',
      f.params      = ['B','Σ_f','D'],
      f.output      = 'covariance_matrix';

MERGE (f:Formula {id: 'f_shrinkage'})
  SET f.name       = 'Ledoit-Wolf Shrinkage Estimator',
      f.expression = 'Σ̂_shrink = (1-λ)·Σ̂_sample + λ·F',
      f.`latex`     = '\\hat{\\Sigma}_{\\text{shrink}} = (1-\\lambda)\\hat{\\Sigma}_{\\text{sample}} + \\lambda F',
      f.params      = ['λ','Σ̂_sample','F'],
      f.output      = 'covariance_matrix';

MERGE (f:Formula {id: 'f_factor_beta'})
  SET f.name       = 'Factor Loading (Beta)',
      f.expression = 'β_ik = Cov(R_i, f_k) / Var(f_k)',
      f.`latex`     = '\\beta_{ik} = \\frac{\\text{Cov}(R_i, f_k)}{\\text{Var}(f_k)}',
      f.params      = ['R_i','f_k'],
      f.output      = 'factor_loading';

MERGE (f:Formula {id: 'f_factor_alpha'})
  SET f.name       = 'Factor Alpha',
      f.expression = 'α_i = E[R_i] - βᵢᵀ·E[f]',
      f.`latex`     = '\\alpha_i = \\mathbb{E}[R_i] - \\boldsymbol{\\beta}_i^\\top \\mathbb{E}[\\mathbf{f}]',
      f.params      = ['E_Ri','β_i','E_f'],
      f.output      = 'abnormal_return';

MERGE (f:Formula {id: 'f_rsquared'})
  SET f.name       = 'R-Squared',
      f.expression = 'R² = 1 - Var(ε) / Var(R)',
      f.`latex`     = 'R^2 = 1 - \\frac{\\text{Var}(\\varepsilon)}{\\text{Var}(R)}',
      f.params      = ['Var_ε','Var_R'],
      f.output      = 'explanatory_power';

MERGE (f:Formula {id: 'f_factor_attribution'})
  SET f.name       = 'Factor Return Attribution',
      f.expression = 'R_p = Σ_k β_pk·f_k + α_p',
      f.`latex`     = 'R_p = \\sum_k \\beta_{pk} f_k + \\alpha_p',
      f.params      = ['β_pk','f_k','α_p'],
      f.output      = 'portfolio_return_decomposition';
// -----------------------------------------------------------------------------
// 20. CONCEPT → FORMULA RELATIONSHIPS (v0.2.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Factor Model'}),         (f:Formula {id:'f_factor_model'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'CAPM'}),                 (f:Formula {id:'f_capm'})             MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'APT'}),                  (f:Formula {id:'f_apt'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Risk Model'}),            (f:Formula {id:'f_risk_model'})       MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Covariance Shrinkage'}),  (f:Formula {id:'f_shrinkage'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Ledoit-Wolf Shrinkage'}), (f:Formula {id:'f_shrinkage'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Factor Loading (Beta)'}), (f:Formula {id:'f_factor_beta'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Alpha (Factor)'}),        (f:Formula {id:'f_factor_alpha'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'R-Squared'}),             (f:Formula {id:'f_rsquared'})         MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Factor Attribution'}),    (f:Formula {id:'f_factor_attribution'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Fama-French 3-Factor'}),  (f:Formula {id:'f_factor_model'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Fama-French 5-Factor'}),  (f:Formula {id:'f_factor_model'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Carhart 4-Factor'}),      (f:Formula {id:'f_factor_model'})     MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 21. STRATEGY NODES — FACTOR BATCH (3 new tradeable strategies)
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'Factor Momentum Rotation'})
  SET s.derived_from       = 'Factor Momentum',
      s.description        = 'Long top-quartile factor momentum; short bottom-quartile. Rotate monthly.',
      s.formula_ref        = 'f_factor_model',
      s.sizing_formula_ref = 'f_kelly',
      s.param_lookback     = 12,
      s.param_skip         = 1,
      s.param_top_pct      = 0.25,
      s.risk_weight        = 0.65,
      s.status             = 'active',
      s.target_ticker      = 'QQQ';

MERGE (s:Strategy {name: 'Multi-Factor Long-Short'})
  SET s.derived_from       = 'Fama-French 5-Factor',
      s.description        = 'Combine value, momentum, quality, low-vol signals via risk model. Market-neutral.',
      s.formula_ref        = 'f_factor_attribution',
      s.sizing_formula_ref = 'f_risk_model',
      s.param_max_net_exp  = 0.1,
      s.param_factors      = 'value;momentum;quality;low_vol',
      s.risk_weight        = 0.7,
      s.status             = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Smart Beta Tilt'})
  SET s.derived_from       = 'Smart Beta',
      s.description        = 'Overweight high-quality, low-vol xStocks relative to equal-weight benchmark.',
      s.formula_ref        = 'f_factor_beta',
      s.sizing_formula_ref = 'f_sharpe',
      s.param_quality_min  = 0.6,
      s.param_vol_max      = 0.25,
      s.risk_weight        = 0.5,
      s.status             = 'active',
      s.target_ticker      = 'XLF';


// -----------------------------------------------------------------------------
// 22. NEW STRATEGY → CONCEPT RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Factor Momentum Rotation'}), (c:Concept {name:'Factor Momentum'})      MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (c:Concept {name:'Fama-French 5-Factor'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (c:Concept {name:'Smart Beta'})           MERGE (s)-[:DERIVED_FROM]->(c);


// -----------------------------------------------------------------------------
// 23. NEW STRATEGY → FORMULA RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Factor Momentum Rotation'}), (f:Formula {id:'f_factor_model'})       MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Factor Momentum Rotation'}), (f:Formula {id:'f_kelly'})              MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (f:Formula {id:'f_factor_attribution'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (f:Formula {id:'f_risk_model'})         MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (f:Formula {id:'f_shrinkage'})          MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (f:Formula {id:'f_factor_beta'})        MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (f:Formula {id:'f_sharpe'})             MERGE (s)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 24. NEW STRATEGY → REGIME (ACTIVATED_BY) RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Factor Momentum Rotation'}), (r:Regime {name:'Trending'})       MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Factor Momentum Rotation'}), (r:Regime {name:'Recovery'})       MERGE (s)-[:ACTIVATED_BY {weight:0.65}]->(r);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (r:Regime {name:'LowVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.80}]->(r);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (r:Regime {name:'MeanReverting'})  MERGE (s)-[:ACTIVATED_BY {weight:0.70}]->(r);
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}),  (r:Regime {name:'Trending'})       MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (r:Regime {name:'LowVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.75}]->(r);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (r:Regime {name:'MeanReverting'})  MERGE (s)-[:ACTIVATED_BY {weight:0.60}]->(r);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (r:Regime {name:'Recovery'})       MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);


// -----------------------------------------------------------------------------
// 25. EXTENDED CONTRADICTED_BY — FACTOR STRATEGIES vs. OPTIONS STRATEGIES
// Prevents agent from simultaneously running conflicting risk profiles
// -----------------------------------------------------------------------------

// Factor momentum conflicts with volatility mean reversion (opposite directional bets)
MATCH (a:Strategy {name:'Factor Momentum Rotation'}), (b:Strategy {name:'Volatility Mean Reversion'}) MERGE (a)-[:CONTRADICTED_BY]->(b);

// Multi-factor market-neutral conflicts with directional momentum breakout
MATCH (a:Strategy {name:'Multi-Factor Long-Short'}),  (b:Strategy {name:'Momentum Breakout'})         MERGE (a)-[:CONTRADICTED_BY]->(b);

// Smart Beta (long-only tilt) conflicts with Delta-Neutral Carry (requires balanced book)
MATCH (a:Strategy {name:'Smart Beta Tilt'}),          (b:Strategy {name:'Delta-Neutral Carry'})       MERGE (a)-[:CONTRADICTED_BY]->(b);

// =============================================================================
// END v0.2.0
// -----------------------------------------------------------------------------
// KG STATS AFTER v0.2.0 LOAD:
//   Concept nodes     : 65  (29 options/vol + 36 factor/estimation)
//   Category nodes    : 21
//   Formula nodes     : 25  (16 + 9 new)
//   Strategy nodes    : 8   (5 + 3 new)
//   Regime nodes      : 6
//   Ticker nodes      : 10
//   PREREQ_OF edges   : ~58 (24 + ~34 new)
//   ACTIVATED_BY edges: 18  (10 + 8 new)
//   CONTRADICTED_BY   : 5   (2 + 3 new)
//   HAS_FORMULA edges : ~30 (17 + ~13 new)
// =============================================================================


// =============================================================================
// v0.3.0 ADDITIONS — SYSTEMIC RISK & MACROECONOMIC INDICATORS
// Source: "Systemic Risk: Macroeconomic Indicators" (Bisias et al. survey)
// Domains: systemic_risk, network_theory, macroprudential, shadow_banking,
//          contagion, stress_testing, complexity_theory, risk_management
// -----------------------------------------------------------------------------
// New concepts  : 28
// New categories: 8
// New formulas  : 6
// New strategies: 2  (systemic-risk-aware overlays)
// New regime    : 1  (Systemic Stress)
// Key new rel types: TRANSMITS_TO, REGULATES, AMPLIFIES, MONITORS
// =============================================================================


// -----------------------------------------------------------------------------
// 26. SCHEMA VERSION BUMP
// -----------------------------------------------------------------------------

// Schema version: 0.3.0
// Changelog:
//   0.3.0 — Systemic risk, network contagion, shadow banking, non-stationarity,
//            macroprudential/microprudential regulation, stress testing,
//            complexity & emergent properties. Source: Bisias et al. (2012).


// -----------------------------------------------------------------------------
// 27. NEW CATEGORY NODES
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'systemic_risk',       display: 'Systemic Risk'});
MERGE (:Category {name: 'network_theory',       display: 'Network Theory'});
MERGE (:Category {name: 'macroprudential',      display: 'Macroprudential Policy'});
MERGE (:Category {name: 'shadow_banking',       display: 'Shadow Banking'});
MERGE (:Category {name: 'contagion',            display: 'Contagion & Transmission'});
MERGE (:Category {name: 'stress_testing',       display: 'Stress Testing'});
MERGE (:Category {name: 'complexity_theory',    display: 'Complexity Theory'});
MERGE (:Category {name: 'macro_indicators',     display: 'Macroeconomic Indicators'});


// -----------------------------------------------------------------------------
// 28. NEW MARKET REGIME — SYSTEMIC STRESS
// Extends the regime taxonomy with a crisis-precursor state distinct from Crisis
// -----------------------------------------------------------------------------

MERGE (r:Regime {name: 'SystemicStress'})
  SET r.description =      'Densifying interbank network, rising contagion probability, shadow banking expansion, pre-crisis liquidity pressure',
      r.momentum_score =   0.15,
      r.vol_level =        'extreme',
      r.network_density =  'high',
      r.shadow_share =     'elevated';


// -----------------------------------------------------------------------------
// 29. CONCEPT NODES — SYSTEMIC RISK BATCH
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Systemic Risk'})
  SET c.definition   = 'Risk of collapse of an entire financial system or market, distinct from idiosyncratic risk of individual components. An emergent property of complex financial networks.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Non-Stationarity'})
  SET c.definition   = 'Statistical property where the data-generating process changes over time. The distribution, mean, or variance of returns shifts, invalidating backward-looking risk models. Systemic risk is a prime illustration.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Emergent Property'})
  SET c.definition   = 'System-level feature that arises only from dense interactions between components and cannot be predicted from analyzing any individual component in isolation. Systemic risk is emergent.',
      c.category     = 'complexity_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Fallacy of Composition'})
  SET c.definition   = 'Error of inferring that system-level behavior is simply the aggregate of individual behaviors. Patterns in market dynamics at system level are distinct from the sum of individual participants.',
      c.category     = 'complexity_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Financial Network'})
  SET c.definition   = 'Graph where nodes are financial entities (banks, funds, insurers) and edges are financial contracts or exposures. Enables modeling of contagion paths and indirect exposure.',
      c.category     = 'network_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Interbank Network'})
  SET c.definition   = 'Subgraph of the financial network representing bilateral lending and exposure relationships between banks. Densification of this network increases systemic contagion risk.',
      c.category     = 'network_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Network Densification'})
  SET c.definition   = 'Increasing number of connections per node in the financial network over time. Each added edge creates new contagion pathways. Observed empirically in Chinese and global interbank systems.',
      c.category     = 'network_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Contagion'})
  SET c.definition   = 'Transmission of financial distress from one entity or market to others via direct exposures, fire sales, or loss of confidence. Can propagate through multiple hops in the financial network.',
      c.category     = 'contagion',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Direct Counterparty Exposure'})
  SET c.definition   = 'First-order financial obligation between two entities. Loss by one party creates immediate credit risk for the other. First hop in contagion chain.',
      c.category     = 'contagion',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Indirect Exposure'})
  SET c.definition   = 'Secondary or tertiary financial exposure arising via common counterparties or shared asset holdings. Entities without direct relationships still face contagion risk through network paths.',
      c.category     = 'contagion',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Shadow Banking'})
  SET c.definition   = 'Financial intermediation conducted by non-bank entities (hedge funds, money market funds, SPVs) outside traditional banking regulation. Conducts bank-like financing without bank-level regulatory oversight.',
      c.category     = 'shadow_banking',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Schwarz 2012';

MERGE (c:Concept {name: 'Disintermediation'})
  SET c.definition   = 'Removal of traditional bank intermediaries from financial transactions. Borrowers and lenders connect directly or via non-bank entities. Increases efficiency but reduces regulatory visibility.',
      c.category     = 'shadow_banking',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Regulatory Arbitrage'})
  SET c.definition   = 'Structuring financial activity to exploit differences in regulatory regimes across entities, jurisdictions, or instruments. Shadow banking growth is partly driven by regulatory arbitrage.',
      c.category     = 'shadow_banking',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Off-Balance-Sheet Risk'})
  SET c.definition   = 'Risk arising from entities or exposures not captured on a firm\'s formal balance sheet. SPVs and conduits shift assets off-balance-sheet, obscuring true systemic exposure.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Macroprudential Regulation'})
  SET c.definition   = 'System-wide regulatory approach targeting aggregate financial stability rather than individual firm soundness. Addresses procyclicality, interconnectedness, and too-big-to-fail institutions.',
      c.category     = 'macroprudential',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Microprudential Regulation'})
  SET c.definition   = 'Entity-level regulatory approach focused on the soundness of individual financial institutions. Necessary but insufficient for systemic risk management due to fallacy of composition.',
      c.category     = 'macroprudential',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Procyclicality'})
  SET c.definition   = 'Tendency of financial system to amplify economic cycles: excessive risk-taking in booms, excessive deleveraging in busts. A key macroprudential concern.',
      c.category     = 'macroprudential',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Too-Big-To-Fail'})
  SET c.definition   = 'Characterization of systemically important institutions whose failure would trigger broader financial collapse, creating implicit government guarantee and moral hazard.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Stress Testing'})
  SET c.definition   = 'Forward-looking risk assessment technique applying severe but plausible macroeconomic scenarios to portfolios or institutions to estimate losses under stress conditions.',
      c.category     = 'stress_testing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Scenario Analysis'})
  SET c.definition   = 'Structured examination of portfolio or system behavior under specified alternative states of the world. Complements VaR by capturing non-linear and tail risk not visible in historical distributions.',
      c.category     = 'stress_testing',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Fire Sale'})
  SET c.definition   = 'Forced liquidation of assets at below-fundamental prices, typically under margin calls or redemption pressure. Creates negative externalities through price impact on holders of similar assets.',
      c.category     = 'contagion',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Liquidity Spiral'})
  SET c.definition   = 'Self-reinforcing feedback loop: falling asset prices → margin calls → forced sales → further price falls → tighter funding → more forced sales. Amplifies contagion dramatically.',
      c.category     = 'contagion',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Systemic Risk Measurement'})
  SET c.definition   = 'Translation of economic systemic risk concepts into quantitative measures. Requires decisions on which entities to measure, observation frequency, granularity, and aggregation method.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'CoVaR'})
  SET c.definition   = 'Conditional Value at Risk of the financial system given that a particular institution is in distress. ΔCoVaR = CoVaR|distress - CoVaR|median. Measures marginal systemic risk contribution.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Adrian & Brunnermeier 2016';

MERGE (c:Concept {name: 'SRISK'})
  SET c.definition   = 'Systemic risk measure: expected capital shortfall of a firm in a severe market decline. SRISK = max(0, k(Debt + Equity·LRMES) - Equity·(1-LRMES)). Captures size, leverage, and tail dependence.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Acharya et al. 2012';

MERGE (c:Concept {name: 'Network Centrality'})
  SET c.definition   = 'Graph-theoretic measure of a node\'s importance in a network. In financial networks, high-centrality institutions are potential super-spreaders of contagion. Includes degree, betweenness, eigenvector centrality.',
      c.category     = 'network_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Systemic Importance Score'})
  SET c.definition   = 'Composite score combining size, interconnectedness, substitutability, and cross-jurisdictional activity to rank G-SIBs (Global Systemically Important Banks).',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Financial Stability Monitoring'})
  SET c.definition   = 'Continuous observation and measurement of systemic risk indicators across the financial system. Requires diverse perspectives and adaptive re-evaluation as system structure evolves.',
      c.category     = 'macroprudential',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';


// -----------------------------------------------------------------------------
// 30. NEW CONCEPT → CATEGORY RELATIONSHIPS (v0.3.0 batch)
// -----------------------------------------------------------------------------

MATCH (c:Concept), (cat:Category)
WHERE c.category = cat.name
  AND c.menu_context = 'RiskMgr'
MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// 31. PREREQUISITE RELATIONSHIPS — SYSTEMIC RISK BATCH
// Models the conceptual dependency chain from micro to macro risk understanding
// -----------------------------------------------------------------------------

// Foundation: systemic risk understanding requires micro concepts first
MATCH (a:Concept {name:'Risk Model'}),             (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowding'}),               (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Specific Risk'}),          (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);

// Non-stationarity and complexity
MATCH (a:Concept {name:'Non-Stationarity'}),       (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Emergent Property'}),      (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fallacy of Composition'}), (b:Concept {name:'Emergent Property'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fallacy of Composition'}), (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);

// Network theory chain
MATCH (a:Concept {name:'Financial Network'}),      (b:Concept {name:'Interbank Network'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Financial Network'}),      (b:Concept {name:'Network Densification'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Financial Network'}),      (b:Concept {name:'Network Centrality'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Financial Network'}),      (b:Concept {name:'Contagion'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Interbank Network'}),      (b:Concept {name:'Network Densification'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Network Densification'}),  (b:Concept {name:'Contagion'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Network Centrality'}),     (b:Concept {name:'Systemic Importance Score'})MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Network Centrality'}),     (b:Concept {name:'Too-Big-To-Fail'})          MERGE (a)-[:PREREQ_OF]->(b);

// Contagion mechanics
MATCH (a:Concept {name:'Direct Counterparty Exposure'}),(b:Concept {name:'Contagion'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Direct Counterparty Exposure'}),(b:Concept {name:'Indirect Exposure'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Indirect Exposure'}),      (b:Concept {name:'Contagion'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Contagion'}),              (b:Concept {name:'Fire Sale'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fire Sale'}),              (b:Concept {name:'Liquidity Spiral'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Liquidity Spiral'}),       (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Procyclicality'}),         (b:Concept {name:'Liquidity Spiral'})         MERGE (a)-[:PREREQ_OF]->(b);

// Shadow banking chain
MATCH (a:Concept {name:'Disintermediation'}),      (b:Concept {name:'Shadow Banking'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Regulatory Arbitrage'}),   (b:Concept {name:'Shadow Banking'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Shadow Banking'}),         (b:Concept {name:'Off-Balance-Sheet Risk'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Off-Balance-Sheet Risk'}), (b:Concept {name:'Systemic Risk'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Shadow Banking'}),         (b:Concept {name:'Regulatory Arbitrage'})     MERGE (a)-[:PREREQ_OF]->(b);

// Regulation chain
MATCH (a:Concept {name:'Microprudential Regulation'}),(b:Concept {name:'Macroprudential Regulation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Systemic Risk'}),          (b:Concept {name:'Macroprudential Regulation'})MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Too-Big-To-Fail'}),        (b:Concept {name:'Macroprudential Regulation'})MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Procyclicality'}),         (b:Concept {name:'Macroprudential Regulation'})MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Macroprudential Regulation'}),(b:Concept {name:'Financial Stability Monitoring'}) MERGE (a)-[:PREREQ_OF]->(b);

// Measurement chain
MATCH (a:Concept {name:'Systemic Risk'}),          (b:Concept {name:'Systemic Risk Measurement'})MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Systemic Risk Measurement'}),(b:Concept {name:'CoVaR'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Systemic Risk Measurement'}),(b:Concept {name:'SRISK'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Systemic Risk Measurement'}),(b:Concept {name:'Systemic Importance Score'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),       (b:Concept {name:'Systemic Risk Measurement'})MERGE (a)-[:PREREQ_OF]->(b);

// Stress testing
MATCH (a:Concept {name:'Systemic Risk Measurement'}),(b:Concept {name:'Stress Testing'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Stress Testing'}),         (b:Concept {name:'Scenario Analysis'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),       (b:Concept {name:'Stress Testing'})           MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain bridges: options/vol → systemic risk
MATCH (a:Concept {name:'Jump Diffusion'}),         (b:Concept {name:'Contagion'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Liquidity Spiral'}),       (b:Concept {name:'Fire Sale'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowding'}),               (b:Concept {name:'Fire Sale'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowding'}),               (b:Concept {name:'Liquidity Spiral'})         MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain bridges: factor → systemic risk
MATCH (a:Concept {name:'Factor Capacity'}),        (b:Concept {name:'Crowding'})                 MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Low Volatility Anomaly'}), (b:Concept {name:'Procyclicality'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Covariance Shrinkage'}),   (b:Concept {name:'Systemic Risk Measurement'})MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// 32. NEW RELATIONSHIP TYPE: TRANSMITS_TO
// Directional contagion edges between concept-level risk nodes.
// The agent uses these to trace propagation paths in crisis regimes.
// Format: (source risk concept)-[:TRANSMITS_TO {speed, severity}]->(target)
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Fire Sale'}),        (b:Concept {name:'Liquidity Spiral'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'high',   mechanism:'price_impact'}]->(b);

MATCH (a:Concept {name:'Liquidity Spiral'}), (b:Concept {name:'Contagion'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'extreme', mechanism:'funding_withdrawal'}]->(b);

MATCH (a:Concept {name:'Shadow Banking'}),   (b:Concept {name:'Off-Balance-Sheet Risk'})
  MERGE (a)-[:TRANSMITS_TO {speed:'slow', severity:'high',   mechanism:'regulatory_gap'}]->(b);

MATCH (a:Concept {name:'Network Densification'}),(b:Concept {name:'Contagion'})
  MERGE (a)-[:TRANSMITS_TO {speed:'medium', severity:'high', mechanism:'indirect_exposure'}]->(b);

MATCH (a:Concept {name:'Procyclicality'}),   (b:Concept {name:'Fire Sale'})
  MERGE (a)-[:TRANSMITS_TO {speed:'medium', severity:'high', mechanism:'margin_calls'}]->(b);

MATCH (a:Concept {name:'Contagion'}),        (b:Concept {name:'Systemic Risk'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'extreme', mechanism:'network_cascade'}]->(b);


// -----------------------------------------------------------------------------
// 33. NEW RELATIONSHIP TYPE: MONITORS / REGULATES
// Links regulatory concepts to risk concepts they are designed to address.
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Macroprudential Regulation'}), (b:Concept {name:'Systemic Risk'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Macroprudential Regulation'}), (b:Concept {name:'Procyclicality'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Macroprudential Regulation'}), (b:Concept {name:'Shadow Banking'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Macroprudential Regulation'}), (b:Concept {name:'Too-Big-To-Fail'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Financial Stability Monitoring'}),(b:Concept {name:'Network Densification'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Financial Stability Monitoring'}),(b:Concept {name:'Contagion'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Microprudential Regulation'}), (b:Concept {name:'Direct Counterparty Exposure'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Stress Testing'}),             (b:Concept {name:'Systemic Risk'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'CoVaR'}),                      (b:Concept {name:'Contagion'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'SRISK'}),                      (b:Concept {name:'Too-Big-To-Fail'})
  MERGE (a)-[:MONITORS]->(b);


// -----------------------------------------------------------------------------
// 34. FORMULA NODES — SYSTEMIC RISK BATCH
// -----------------------------------------------------------------------------
MERGE (f:Formula {id: 'f_covar'})
  SET f.name       = 'CoVaR (Conditional Value at Risk)',
      f.expression = 'ΔCoVaR_i = CoVaR|distress_i - CoVaR|median_i',
      f.`latex`     = '\\Delta\\text{CoVaR}_i = \\text{CoVaR}^{system|X_i=\\text{distress}} - \\text{CoVaR}^{system|X_i=\\text{median}}',
      f.params      = ['VaR_i','conditioning_quantile','joint_distribution'],
      f.output      = 'systemic_risk_contribution';

MERGE (f:Formula {id: 'f_srisk'})
  SET f.name       = 'SRISK (Expected Capital Shortfall)',
      f.expression = 'SRISK_i = max(0, k(Debt_i + Equity_i·LRMES_i) - Equity_i·(1-LRMES_i))',
      f.`latex`     = 'SRISK_i = \\max\\bigl(0,\\; k(D_i + E_i \\cdot LRMES_i) - E_i(1-LRMES_i)\\bigr)',
      f.params      = ['k','Debt','Equity','LRMES'],
      f.output      = 'capital_shortfall';

MERGE (f:Formula {id: 'f_lrmes'})
  SET f.name       = 'Long-Run Marginal Expected Shortfall (LRMES)',
      f.expression = 'LRMES_i ≈ 1 - exp(log(1 - MES_i) × h)',
      f.`latex`     = 'LRMES_i \\approx 1 - \\exp\\!\\bigl(\\ln(1-MES_i)\\cdot h\\bigr)',
      f.params      = ['MES_i','h'],
      f.output      = 'long_run_equity_loss';

MERGE (f:Formula {id: 'f_network_centrality'})
  SET f.name       = 'Eigenvector Centrality (Financial Network)',
      f.expression = 'x_i = (1/λ) · Σ_j A_ij · x_j',
      f.`latex`     = 'x_i = \\frac{1}{\\lambda}\\sum_j A_{ij} x_j',
      f.params      = ['A_ij','λ','x_j'],
      f.output      = 'centrality_score';

MERGE (f:Formula {id: 'f_contagion_prob'})
  SET f.name       = 'Network Contagion Probability (simplified)',
      f.expression = 'P(contagion) = 1 - Π_j(1 - p_ij · I_j)',
      f.`latex`     = 'P(\\text{contagion}_i) = 1 - \\prod_j (1 - p_{ij} \\cdot I_j)',
      f.params      = ['p_ij','I_j'],
      f.output      = 'contagion_probability';

MERGE (f:Formula {id: 'f_stress_loss'})
  SET f.name       = 'Stress Test Loss Estimate',
      f.expression = 'L_stress = Σ_i w_i · Loss_i(scenario)',
      f.`latex`     = 'L_{\\text{stress}} = \\sum_i w_i \\cdot \\ell_i(\\text{scenario})',
      f.params      = ['w_i','scenario','Loss_i'],
      f.output      = 'portfolio_stress_loss';
// -----------------------------------------------------------------------------
// 35. CONCEPT → FORMULA RELATIONSHIPS (v0.3.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'CoVaR'}),                  (f:Formula {id:'f_covar'})            MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'SRISK'}),                  (f:Formula {id:'f_srisk'})            MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'SRISK'}),                  (f:Formula {id:'f_lrmes'})            MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Network Centrality'}),     (f:Formula {id:'f_network_centrality'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Contagion'}),              (f:Formula {id:'f_contagion_prob'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Interbank Network'}),      (f:Formula {id:'f_contagion_prob'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Stress Testing'}),         (f:Formula {id:'f_stress_loss'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Scenario Analysis'}),      (f:Formula {id:'f_stress_loss'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Systemic Risk Measurement'}),(f:Formula {id:'f_covar'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Systemic Risk Measurement'}),(f:Formula {id:'f_srisk'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Systemic Importance Score'}),(f:Formula {id:'f_network_centrality'}) MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 36. STRATEGY NODES — SYSTEMIC RISK OVERLAYS
// These are not stand-alone alpha strategies but risk overlays the agent
// activates in SystemicStress and Crisis regimes to reduce exposure.
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'Systemic Risk Hedge'})
  SET s.derived_from       = 'CoVaR',
      s.description        = 'In SystemicStress/Crisis regime: reduce net exposure, short high-CoVaR names, increase cash. Uses CoVaR ranking of xStock tickers.',
      s.formula_ref        = 'f_covar',
      s.sizing_formula_ref = 'f_srisk',
      s.param_covar_threshold = 0.05,
      s.param_max_gross_exp   = 0.4,
      s.risk_weight        = 0.9,
      s.strategy_type      = 'overlay',
      s.status             = 'active',
      s.target_ticker      = 'GLD';

MERGE (s:Strategy {name: 'Contagion Path Avoidance'})
  SET s.derived_from       = 'Financial Network',
      s.description        = 'Avoid positions in tickers with high network centrality (super-spreaders) when contagion probability exceeds threshold. Uses graph traversal on CORRELATED_WITH network.',
      s.formula_ref        = 'f_network_centrality',
      s.sizing_formula_ref = 'f_contagion_prob',
      s.param_centrality_max  = 0.7,
      s.param_contagion_prob_max = 0.3,
      s.risk_weight        = 0.95,
      s.strategy_type      = 'overlay',
      s.status             = 'active',
      s.target_ticker      = 'XLF';


// -----------------------------------------------------------------------------
// 37. NEW STRATEGY → CONCEPT, FORMULA, REGIME RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (c:Concept {name:'CoVaR'})              MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (c:Concept {name:'SRISK'})              MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (c:Concept {name:'Financial Network'})  MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (c:Concept {name:'Network Centrality'}) MERGE (s)-[:DERIVED_FROM]->(c);

MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (f:Formula {id:'f_covar'})              MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (f:Formula {id:'f_srisk'})              MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (f:Formula {id:'f_network_centrality'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (f:Formula {id:'f_contagion_prob'})     MERGE (s)-[:HAS_FORMULA]->(f);

// Overlays activate in ALL high-stress regimes
MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (r:Regime {name:'Crisis'})              MERGE (s)-[:ACTIVATED_BY {weight:1.0}]->(r);
MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (r:Regime {name:'SystemicStress'})      MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'Systemic Risk Hedge'}),       (r:Regime {name:'HighVolatility'})      MERGE (s)-[:ACTIVATED_BY {weight:0.75}]->(r);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (r:Regime {name:'Crisis'})              MERGE (s)-[:ACTIVATED_BY {weight:1.0}]->(r);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (r:Regime {name:'SystemicStress'})      MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'Contagion Path Avoidance'}),  (r:Regime {name:'HighVolatility'})      MERGE (s)-[:ACTIVATED_BY {weight:0.70}]->(r);

// Overlays never conflict with alpha strategies — they suppress them instead
// (agent logic: if overlay active at weight > 0.9, all alpha strategies are paused)


// -----------------------------------------------------------------------------
// 38. NEW AGENT QUERY PATTERNS (v0.3.0)
// Add to graph/queries/ files
// -----------------------------------------------------------------------------

// Q8: Contagion path trace — find all concepts reachable from a shock source
// MATCH path = (shock:Concept {name: $shock_concept})-[:TRANSMITS_TO*1..5]->(target:Concept)
// RETURN [n IN nodes(path) | n.name] AS propagation_path,
//        [r IN relationships(path) | r.mechanism] AS mechanisms,
//        length(path) AS hops
// ORDER BY hops ASC

// Q9: Tickers most exposed to systemic contagion (super-spreaders)
// MATCH (t:Ticker)-[r:CORRELATED_WITH]->(t2:Ticker)
// WITH t, count(r) AS degree, avg(r.weight) AS avg_corr
// WHERE degree > 3 AND avg_corr > 0.6
// RETURN t.symbol, t.name, degree, avg_corr
// ORDER BY degree DESC, avg_corr DESC

// Q10: Regulatory concept map — what does each measure monitor?
// MATCH (reg:Concept)-[:MONITORS]->(risk:Concept)
// RETURN reg.name AS regulator, collect(risk.name) AS monitors
// ORDER BY size(collect(risk.name)) DESC

// Q11: Full systemic risk chain from shadow banking to collapse
// MATCH path = (start:Concept {name:'Shadow Banking'})-[:PREREQ_OF|TRANSMITS_TO*1..8]->(end:Concept {name:'Systemic Risk'})
// RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS depth
// ORDER BY depth ASC LIMIT 5

// =============================================================================
// END v0.3.0
// -----------------------------------------------------------------------------
// KG STATS AFTER v0.3.0 LOAD:
//   Concept nodes     : 93  (65 + 28 systemic risk)
//   Category nodes    : 29  (21 + 8 new)
//   Formula nodes     : 33  (27 + 6 new)
//   Strategy nodes    : 10  (8 + 2 overlay strategies)
//   Regime nodes      : 7   (6 + SystemicStress)
//   Ticker nodes      : 10
//   PREREQ_OF edges   : ~95 (~58 + ~37 new)
//   TRANSMITS_TO edges:   6 (new relationship type)
//   MONITORS edges    :  10 (new relationship type)
//   ACTIVATED_BY edges:  24 (18 + 6 new)
//   CONTRADICTED_BY   :   5 (unchanged — overlays suppress, not contradict)
//   HAS_FORMULA edges : ~57 (~46 + ~11 new)
// Total relationship types: 10
//   PREREQ_OF, BELONGS_TO, HAS_FORMULA, DERIVED_FROM,
//   ACTIVATED_BY, CONTRADICTED_BY, TRANSMITS_TO, MONITORS,
//   CORRELATED_WITH (runtime), HAS_SIGNAL (runtime)
// =============================================================================


// =============================================================================
// v0.4.0 ADDITIONS
// Sources:
//   Doc A — Systemic Risk: Networks & Principal Components (Bisias et al.)
//   Doc B — Systemic Risk: Conditional & Illiquidity Risk (Bisias et al.)
//   Doc C — Systemic Risk Meets Machine Learning (Scaramozzino et al.)
//   Doc D — Trading Volatility: Variance Swaps (Hilpisch)
//   Doc E — Variance Swaps: Spanning with Options (Hilpisch / Demeterfi)
// -----------------------------------------------------------------------------
// New concepts  : 46
// New categories: 7
// New formulas  : 12
// New strategies: 3
// New rel types : REPLICATES_WITH, HEDGES
// =============================================================================

// Schema version: 0.4.0
// Changelog:
//   0.4.0 — Fire sale mechanics, contingent claims/CCA, Granger causality,
//            absorption ratio, PCA systemic exposure, DIP, CoRisk, Kyle's lambda,
//            MES/SES, transfer entropy, information flow, liquidity-information link,
//            variance swaps, volatility swaps, OTC/ISDA/margin mechanics,
//            log contract, spanning with options, Arrow-Debreu/state prices,
//            constant dollar gamma, model-free variance replication,
//            realized vs implied variance, variance swap hedging strategies.


// -----------------------------------------------------------------------------
// 39. NEW CATEGORY NODES (v0.4.0)
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'fire_sale_mechanics',    display: 'Fire Sale Mechanics'});
MERGE (:Category {name: 'contingent_claims',      display: 'Contingent Claims Analysis'});
MERGE (:Category {name: 'granger_causality',      display: 'Granger Causality'});
MERGE (:Category {name: 'information_theory',     display: 'Information Theory'});
MERGE (:Category {name: 'variance_swaps',         display: 'Variance & Volatility Swaps'});
MERGE (:Category {name: 'otc_derivatives',        display: 'OTC Derivatives & Margining'});
MERGE (:Category {name: 'replication_theory',     display: 'Replication Theory'});


// -----------------------------------------------------------------------------
// 40. CONCEPT NODES — NETWORKS, PCA & FIRE SALE MECHANICS (Doc A)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Mark-to-Market Accounting'})
  SET c.definition   = 'Accounting method where asset values on balance sheet reflect current market prices. Assets = Liabilities + Equity; falling prices directly reduce equity, triggering margin calls and forced sales.',
      c.category     = 'fire_sale_mechanics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Historical Cost Accounting'})
  SET c.definition   = 'Accounting method where assets are carried at original purchase price. Balance sheet equity is insulated from interim market price movements, reducing procyclical deleveraging pressure.',
      c.category     = 'fire_sale_mechanics',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Leverage Effect (Balance Sheet)'})
  SET c.definition   = 'Amplification of equity losses by balance sheet leverage. High asset/equity ratio means small asset price decline wipes out equity entirely. Key driver of fire sale urgency.',
      c.category     = 'fire_sale_mechanics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Pro-Cyclical Deleveraging'})
  SET c.definition   = 'Self-reinforcing process where mark-to-market losses force asset sales which depress prices further, forcing more sales. Amplifies downturns beyond fundamentals.',
      c.category     = 'fire_sale_mechanics',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Cross-Asset Contagion'})
  SET c.definition   = 'Transmission of distress to unrelated assets. Firm sells liquid unaffected assets (XYZ, UVW) to avoid locking in losses on distressed holdings (ABC, DEF), spreading price pressure across asset classes.',
      c.category     = 'contagion',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Contingent Claims Analysis (CCA)'})
  SET c.definition   = 'Merton-model-based framework treating equity as a call option on firm assets and government rescue as a contingent liability. Quantifies implicit government guarantee value for TBTF institutions.',
      c.category     = 'contingent_claims',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; frds.io';

MERGE (c:Concept {name: 'Implicit Government Guarantee'})
  SET c.definition   = 'Market belief that government will rescue systemically important institutions despite no explicit contractual commitment. Creates moral hazard; quantified via CCA.',
      c.category     = 'contingent_claims',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Moral Hazard (Financial)'})
  SET c.definition   = 'Tendency to take greater risks when costs of failure are borne by another party. TBTF institutions underprice risk because losses are implicitly socialized via government guarantee.',
      c.category     = 'contingent_claims',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Resolution Plan (Living Will)'})
  SET c.definition   = 'Regulatory requirement under Dodd-Frank for large institutions to document orderly wind-down strategy. Designed to make TBTF institutions resolvable without government rescue.',
      c.category     = 'macroprudential',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Federal Reserve';

MERGE (c:Concept {name: 'Granger Causality'})
  SET c.definition   = 'Statistical test of predictive causality: X Granger-causes Y if past values of X contain information that predicts Y beyond Y\'s own past. Directional measure used to build financial causality networks.',
      c.category     = 'granger_causality',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Scholarpedia';

MERGE (c:Concept {name: 'Granger Causality Matrix'})
  SET c.definition   = 'N×N matrix of p-values from pairwise Granger causality tests. Entry (i,j) is p-value for X_j G-causing X_i. Low p-value indicates causality. Used to construct adjacency matrix for network analysis.',
      c.category     = 'granger_causality',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Adjacency Matrix'})
  SET c.definition   = 'Binary N×N matrix A where A_ij=1 if Granger causality exists from j to i (p-value below threshold), else 0. Input to eigenvector centrality and NetworkX graph construction.',
      c.category     = 'network_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Absorption Ratio'})
  SET c.definition   = 'AR = (Σ_{k=1}^{n} σ²_{fk}) / (Σ_{i=1}^{N} σ²_{Ai}). Fraction of total variance absorbed by top-n eigenvectors. Rising AR signals increasing systemic risk as a hidden market factor drives correlated returns.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'PCA Systemic Exposure'})
  SET c.definition   = 'Sum of a firm\'s exposures across top-K principal components of the system-wide return covariance. Measures breadth of a firm\'s systemic footprint. K is a tunable hyperparameter (Bisias: K=20).',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';


// -----------------------------------------------------------------------------
// 41. CONCEPT NODES — CONDITIONAL & ILLIQUIDITY RISK (Doc B)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Distressed Insurance Premium (DIP)'})
  SET c.definition   = 'Expected shortfall of the banking system conditional on systemic distress (≥15% credit asset losses). Computed as risk-neutral cost of insuring aggregate credit losses. Inputs: PDs, correlation matrix, distress threshold.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Huang et al. 2011';

MERGE (c:Concept {name: 'Probability of Default (PD)'})
  SET c.definition   = 'Likelihood that a borrower fails to meet debt obligations. Backed out from CDS spread: PD ≈ CDS_spread / (1 - Recovery_rate). Key input to DIP and CCA models.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Loss Given Default (LGD)'})
  SET c.definition   = 'Fraction of exposure lost when counterparty defaults. LGD = 1 - Recovery Rate. Determines severity component of expected credit loss: EL = PD × LGD × EAD.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'CoRisk'})
  SET c.definition   = 'Quantile-regression-based measure of credit contagion. Predicts % increase in firm j\'s CDS spread conditioned on firm i\'s spread being at its 95th percentile. Produces directional contagion network.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Quantile Regression'})
  SET c.definition   = 'Regression estimating effect of independent variable on a specified quantile (e.g., 95th percentile) of the dependent variable\'s distribution. Used in CoVaR and CoRisk to condition on tail events.',
      c.category     = 'statistics',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Ford';

MERGE (c:Concept {name: 'Marginal Expected Shortfall (MES)'})
  SET c.definition   = 'Expected equity loss of firm i when the market falls beyond its VaR threshold. MES_i = E[R_i | R_m < VaR_m]. Short-run component of SRISK. Measures firm\'s tail co-movement with system.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Acharya et al.';

MERGE (c:Concept {name: 'Systemic Expected Shortfall (SES)'})
  SET c.definition   = 'Expected capital shortfall of firm i during a systemic crisis. Combines MES (tail co-movement) with leverage. Positive SES identifies undercapitalized systemically dangerous institutions.',
      c.category     = 'systemic_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Acharya et al.';

MERGE (c:Concept {name: "Kyle's Lambda"})
  SET c.definition   = 'Price impact coefficient λ from Kyle (1985): ΔP = λ·Q where Q is order flow. Measures market illiquidity as the price movement per unit of trade volume. Higher λ = less liquid market.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012; Kyle 1985';

MERGE (c:Concept {name: 'Market Illiquidity'})
  SET c.definition   = 'Inability to execute trades at fair value without significant price impact or delay. Measured by bid-ask spread, Kyle\'s lambda, Amihud ratio. Amplifies contagion during stress.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'CDS Spread'})
  SET c.definition   = 'Annual premium paid by protection buyer to protection seller in a credit default swap. Proxy for market-implied probability of default. CDS markets more liquid than bond markets.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Crowded Trade Risk'})
  SET c.definition   = 'Risk that many market participants hold similar positions. Unwinding creates fire sale contagion. Observed in Quant Meltdown August 2007 (factor crowding) and LTCM 1998.',
      c.category     = 'contagion',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MERGE (c:Concept {name: 'Concentration Risk'})
  SET c.definition   = 'Risk from high correlation across portfolio holdings or banking system assets. Huang et al.: rising concentration risk (correlation) preceded onset of 2007-09 financial crisis.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Huang et al. 2011';


// -----------------------------------------------------------------------------
// 42. CONCEPT NODES — MACHINE LEARNING & TRANSFER ENTROPY (Doc C)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Transfer Entropy'})
  SET c.definition   = 'Information-theoretic measure of directed information flow. TE(X→Y) = conditional mutual information between past of X and future of Y given past of Y. Nonlinear, model-free analog of Granger causality.',
      c.category     = 'information_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Scaramozzino et al. 2021';

MERGE (c:Concept {name: 'Mutual Information'})
  SET c.definition   = 'I(X;Y) = H(X) + H(Y) - H(X,Y). Symmetric measure of statistical dependence between two variables. Generalizes correlation to non-linear relationships. Building block for transfer entropy.',
      c.category     = 'information_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Scaramozzino et al. 2021';

MERGE (c:Concept {name: 'Information-Theoretic Causality'})
  SET c.definition   = 'Framework using entropy and mutual information to detect directional causality between time series. Combines transfer entropy with sentiment and price data to map cross-domain information flow.',
      c.category     = 'information_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Scaramozzino et al. 2021';

MERGE (c:Concept {name: 'Liquidity-Information Flow Link'})
  SET c.definition   = 'Empirical relationship: more liquid markets transmit information faster. CDS markets (more liquid than bonds) show increasing importance as information flow channels. Illiquidity dampens price discovery.',
      c.category     = 'information_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Scaramozzino et al. 2021; Das et al. 2011';

MERGE (c:Concept {name: 'Bin Size (Entropy Estimation)'})
  SET c.definition   = 'Discretization parameter for estimating entropy from continuous data. Crucial hyperparameter: too few bins loses resolution, too many creates sparsity. Scaramozzino: appropriate bin choice is critical.',
      c.category     = 'information_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Scaramozzino et al. 2021';

MERGE (c:Concept {name: 'Sentiment-Price Information Flow'})
  SET c.definition   = 'Directional information transmission between textual sentiment signals (soft data) and asset price series (hard data). Measured via transfer entropy. Sentiment increasingly leads price in CDS markets.',
      c.category     = 'information_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Scaramozzino et al. 2021';


// -----------------------------------------------------------------------------
// 43. CONCEPT NODES — VARIANCE SWAPS (Docs D & E)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Variance Swap'})
  SET c.definition   = 'OTC derivative that pays the difference between realized variance and strike variance: Payoff = N·(σ²_realized - K²_var). Provides direct, model-free exposure to variance without delta exposure to the underlying.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Volatility Swap'})
  SET c.definition   = 'OTC derivative paying the difference between realized volatility and the volatility strike: Payoff = N·(σ_realized - K_vol). Harder to replicate than variance swap due to square root non-linearity.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Realized Variance'})
  SET c.definition   = 'σ²_realized = (252/N)·Σ(ln(S_t/S_{t-1}))². Annualized sum of squared log returns over the swap observation period. Determines the floating leg payment of a variance swap.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'Variance Swap Strike (K_var)'})
  SET c.definition   = 'Fair value of the fixed leg: K²_var = E^Q[σ²_realized]. Set at trade inception so swap has zero initial value. Related to implied volatility but not equal due to convexity.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Log Contract'})
  SET c.definition   = 'Hypothetical contract with payoff ln(S_T/S_0). Not actually traded, but its replication via a strip of options with the second-order term equal to realized variance makes it the theoretical foundation of variance swap pricing.',
      c.category     = 'replication_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Neuberger 1994';

MERGE (c:Concept {name: 'Spanning with Options'})
  SET c.definition   = 'Any twice continuously differentiable payoff g(S_T) can be replicated by a static portfolio of European puts and calls across a continuum of strikes. Foundation of model-free variance swap replication.',
      c.category     = 'replication_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Carr & Madan';

MERGE (c:Concept {name: 'State Prices (Arrow-Debreu)'})
  SET c.definition   = 'Price of a contingent claim paying 1 in one state of the world and 0 otherwise. Equal to the risk-neutral probability of that state. Option prices across all strikes encode the full risk-neutral PDF.',
      c.category     = 'replication_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Cochrane';

MERGE (c:Concept {name: 'Risk-Neutral PDF from Options'})
  SET c.definition   = 'Breeden-Litzenberger result: risk-neutral probability density p(K) = e^(rT)·∂²C/∂K² = e^(rT)·∂²P/∂K². Second derivative of call/put price w.r.t. strike gives market-implied probability density.',
      c.category     = 'replication_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Breeden-Litzenberger 1978';

MERGE (c:Concept {name: 'Constant Dollar Gamma'})
  SET c.definition   = 'Dollar gamma = S²·Γ/2. In variance swap replication, each option is weighted by 1/K² so that dollar gamma is constant across all strikes, ensuring equal variance sensitivity regardless of underlying price level.',
      c.category     = 'replication_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Model-Free Variance Replication'})
  SET c.definition   = 'Replication of realized variance using a static strip of options without model assumptions: E^Q[σ²] = (2/T)·[∫₀^F (1/K²)·P(K)dK + ∫_F^∞ (1/K²)·C(K)dK]. Valid under any continuous price process.',
      c.category     = 'replication_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Realized vs Implied Variance Spread'})
  SET c.definition   = 'Difference between ex-post realized variance and ex-ante implied variance (variance swap strike). Variance risk premium: implied typically exceeds realized, reflecting negative variance risk premium in equity markets.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'OTC Derivative'})
  SET c.definition   = 'Bilateral financial contract between two parties negotiated outside an exchange. Allows bespoke terms (strike, maturity, notional). Governed by ISDA Master Agreement. Examples: variance swaps, CDS, exotic options.',
      c.category     = 'otc_derivatives',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'ISDA Master Agreement'})
  SET c.definition   = 'Industry-standard framework agreement (International Swaps and Derivatives Association) governing OTC derivative transactions. Eliminates need to renegotiate all terms per trade. Accompanied by CSA for collateral.',
      c.category     = 'otc_derivatives',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'Credit Support Annex (CSA)'})
  SET c.definition   = 'Annex to ISDA Master Agreement specifying collateral terms for OTC trades. Defines eligible collateral, haircuts, thresholds, and minimum transfer amounts for initial and variation margin.',
      c.category     = 'otc_derivatives',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'Initial Margin (OTC)'})
  SET c.definition   = 'Collateral posted upfront at trade inception to cover potential future exposure. Amount determined by counterparty creditworthiness and trade risk profile. Analogous to down payment on credit risk.',
      c.category     = 'otc_derivatives',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'Variation Margin (OTC)'})
  SET c.definition   = 'Daily mark-to-market settlement of unrealized P&L on OTC positions. Losing party posts collateral daily. Prevents accumulation of large bilateral credit exposures over trade lifetime.',
      c.category     = 'otc_derivatives',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'Dealer Bank'})
  SET c.definition   = 'Investment bank that makes markets in OTC derivatives. Acts as bilateral counterparty for bespoke products like variance swaps, exotic options, and CDS. Manages inventory and hedges residual risk.',
      c.category     = 'otc_derivatives',
      c.difficulty   = 'basic',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch';

MERGE (c:Concept {name: 'Variance Risk Premium'})
  SET c.definition   = 'Implied variance minus expected realized variance. Typically positive (implied > realized) in equity markets, representing compensation for bearing variance risk. Harvestable via short variance swap.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Short Volatility Exposure'})
  SET c.definition   = 'Implicit or explicit position that loses money when realized volatility increases. Risk arbitrageurs, benchmark portfolio managers, and equity long funds are naturally short volatility. Hedgeable via long variance swap.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Long Volatility Exposure'})
  SET c.definition   = 'Implicit or explicit position that profits when realized volatility increases. Options buyers (long gamma) are long volatility. Hedgeable via short variance swap to isolate directional exposure.',
      c.category     = 'variance_swaps',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';


// -----------------------------------------------------------------------------
// 44. NEW CONCEPT → CATEGORY RELATIONSHIPS (v0.4.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept), (cat:Category)
WHERE c.category = cat.name
  AND c.menu_context IN ['RiskMgr', 'Pricer']
WITH c, cat
OPTIONAL MATCH (c)-[r:BELONGS_TO]->(:Category)
WITH c, cat, count(r) AS rel_count
WHERE rel_count = 0
MERGE (c)-[:BELONGS_TO]->(cat);
// -----------------------------------------------------------------------------
// 45. PREREQUISITE RELATIONSHIPS — v0.4.0 FULL BATCH
// -----------------------------------------------------------------------------

// --- Fire Sale Mechanics chain ---
MATCH (a:Concept {name:'Mark-to-Market Accounting'}),  (b:Concept {name:'Pro-Cyclical Deleveraging'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Historical Cost Accounting'}),  (b:Concept {name:'Mark-to-Market Accounting'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Leverage Effect (Balance Sheet)'}),(b:Concept {name:'Fire Sale'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Pro-Cyclical Deleveraging'}),   (b:Concept {name:'Fire Sale'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Pro-Cyclical Deleveraging'}),   (b:Concept {name:'Liquidity Spiral'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Mark-to-Market Accounting'}),   (b:Concept {name:'Cross-Asset Contagion'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Cross-Asset Contagion'}),       (b:Concept {name:'Contagion'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowded Trade Risk'}),          (b:Concept {name:'Cross-Asset Contagion'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowded Trade Risk'}),          (b:Concept {name:'Fire Sale'})                  MERGE (a)-[:PREREQ_OF]->(b);

// --- Contingent Claims chain ---
MATCH (a:Concept {name:'Black-Scholes Model'}),         (b:Concept {name:'Contingent Claims Analysis (CCA)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Risk-Neutral Pricing'}),        (b:Concept {name:'Contingent Claims Analysis (CCA)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Too-Big-To-Fail'}),             (b:Concept {name:'Contingent Claims Analysis (CCA)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Contingent Claims Analysis (CCA)'}),(b:Concept {name:'Implicit Government Guarantee'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implicit Government Guarantee'}),(b:Concept {name:'Moral Hazard (Financial)'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Moral Hazard (Financial)'}),    (b:Concept {name:'Resolution Plan (Living Will)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Too-Big-To-Fail'}),             (b:Concept {name:'Resolution Plan (Living Will)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CDS Spread'}),                  (b:Concept {name:'Probability of Default (PD)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default (PD)'}), (b:Concept {name:'Loss Given Default (LGD)'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default (PD)'}), (b:Concept {name:'Contingent Claims Analysis (CCA)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default (PD)'}), (b:Concept {name:'Distressed Insurance Premium (DIP)'}) MERGE (a)-[:PREREQ_OF]->(b);

// --- Granger Causality chain ---
MATCH (a:Concept {name:'Non-Stationarity'}),            (b:Concept {name:'Granger Causality'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Granger Causality'}),           (b:Concept {name:'Granger Causality Matrix'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Granger Causality Matrix'}),    (b:Concept {name:'Adjacency Matrix'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Adjacency Matrix'}),            (b:Concept {name:'Network Centrality'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Granger Causality Matrix'}),    (b:Concept {name:'PCA Systemic Exposure'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'PCA Factors'}),                 (b:Concept {name:'Absorption Ratio'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'PCA Factors'}),                 (b:Concept {name:'PCA Systemic Exposure'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Absorption Ratio'}),            (b:Concept {name:'Systemic Risk Measurement'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'PCA Systemic Exposure'}),       (b:Concept {name:'Systemic Risk Measurement'})   MERGE (a)-[:PREREQ_OF]->(b);

// --- DIP, CoRisk, MES/SES chain ---
MATCH (a:Concept {name:'Expected Shortfall'}),          (b:Concept {name:'Distressed Insurance Premium (DIP)'}) MERGE (a)-[:PREREQ_OF]->(b);

// Expected Shortfall doesn't exist yet — create it as a bridge concept
MERGE (c:Concept {name: 'Expected Shortfall'})
  SET c.definition   = 'ES_α = -E[R | R < VaR_α]. Expected loss conditional on loss exceeding VaR threshold. More sensitive to tail risk than VaR. Also called Conditional VaR (CVaR). Key input to DIP, MES, SES.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Bisias et al. 2012';

MATCH (c:Concept {name:'Expected Shortfall'}),(cat:Category {name:'risk_metrics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (a:Concept {name:'Expected Shortfall'}),          (b:Concept {name:'Distressed Insurance Premium (DIP)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Expected Shortfall'}),          (b:Concept {name:'Marginal Expected Shortfall (MES)'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Expected Shortfall'}),          (b:Concept {name:'Systemic Expected Shortfall (SES)'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Covariance Shrinkage'}),        (b:Concept {name:'Distressed Insurance Premium (DIP)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Concentration Risk'}),          (b:Concept {name:'Distressed Insurance Premium (DIP)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Marginal Expected Shortfall (MES)'}),(b:Concept {name:'Systemic Expected Shortfall (SES)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Marginal Expected Shortfall (MES)'}),(b:Concept {name:'SRISK'})                        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Quantile Regression'}),         (b:Concept {name:'CoVaR'})                             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Quantile Regression'}),         (b:Concept {name:'CoRisk'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CDS Spread'}),                  (b:Concept {name:'CoRisk'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Market Illiquidity'}),          (b:Concept {name:"Kyle's Lambda"})                     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:"Kyle's Lambda"}),               (b:Concept {name:'Systemic Risk Measurement'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Crowded Trade Risk'}),          (b:Concept {name:'Market Illiquidity'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Concentration Risk'}),          (b:Concept {name:'Systemic Risk'})                     MERGE (a)-[:PREREQ_OF]->(b);

// --- Transfer Entropy chain ---
MATCH (a:Concept {name:'Mutual Information'}),          (b:Concept {name:'Transfer Entropy'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Granger Causality'}),           (b:Concept {name:'Transfer Entropy'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Transfer Entropy'}),            (b:Concept {name:'Information-Theoretic Causality'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Transfer Entropy'}),            (b:Concept {name:'Sentiment-Price Information Flow'})  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Market Illiquidity'}),          (b:Concept {name:'Liquidity-Information Flow Link'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'CDS Spread'}),                  (b:Concept {name:'Liquidity-Information Flow Link'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Liquidity-Information Flow Link'}),(b:Concept {name:'Sentiment-Price Information Flow'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bin Size (Entropy Estimation)'}),(b:Concept {name:'Transfer Entropy'})                 MERGE (a)-[:PREREQ_OF]->(b);

// --- Variance Swap chain ---
MATCH (a:Concept {name:'Geometric Brownian Motion'}),   (b:Concept {name:'Realized Variance'})                 MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Realized Variance'}),           (b:Concept {name:'Variance Swap'})                     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implied Volatility'}),          (b:Concept {name:'Variance Swap Strike (K_var)'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variance Swap Strike (K_var)'}),(b:Concept {name:'Variance Swap'})                     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Realized Variance'}),           (b:Concept {name:'Realized vs Implied Variance Spread'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implied Volatility'}),          (b:Concept {name:'Realized vs Implied Variance Spread'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Realized vs Implied Variance Spread'}),(b:Concept {name:'Variance Risk Premium'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variance Swap'}),               (b:Concept {name:'Volatility Swap'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variance Swap'}),               (b:Concept {name:'Short Volatility Exposure'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variance Swap'}),               (b:Concept {name:'Long Volatility Exposure'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Delta Hedging'}),               (b:Concept {name:'Short Volatility Exposure'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gamma Scalping'}),              (b:Concept {name:'Long Volatility Exposure'})          MERGE (a)-[:PREREQ_OF]->(b);

// --- Replication / Spanning chain ---
MATCH (a:Concept {name:'Risk-Neutral Pricing'}),        (b:Concept {name:'State Prices (Arrow-Debreu)'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'State Prices (Arrow-Debreu)'}), (b:Concept {name:'Risk-Neutral PDF from Options'})     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Risk-Neutral PDF from Options'}),(b:Concept {name:'Spanning with Options'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Spanning with Options'}),       (b:Concept {name:'Log Contract'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Log Contract'}),                (b:Concept {name:'Model-Free Variance Replication'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Constant Dollar Gamma'}),       (b:Concept {name:'Model-Free Variance Replication'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Greeks'}),                      (b:Concept {name:'Constant Dollar Gamma'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Model-Free Variance Replication'}),(b:Concept {name:'Variance Swap Strike (K_var)'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Put-Call Parity'}),             (b:Concept {name:'Spanning with Options'})             MERGE (a)-[:PREREQ_OF]->(b);

// --- OTC / Margining chain ---
MATCH (a:Concept {name:'OTC Derivative'}),              (b:Concept {name:'ISDA Master Agreement'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'ISDA Master Agreement'}),       (b:Concept {name:'Credit Support Annex (CSA)'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Credit Support Annex (CSA)'}),  (b:Concept {name:'Initial Margin (OTC)'})              MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Credit Support Annex (CSA)'}),  (b:Concept {name:'Variation Margin (OTC)'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Mark-to-Market Accounting'}),   (b:Concept {name:'Variation Margin (OTC)'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variance Swap'}),               (b:Concept {name:'OTC Derivative'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Dealer Bank'}),                 (b:Concept {name:'OTC Derivative'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variation Margin (OTC)'}),      (b:Concept {name:'Direct Counterparty Exposure'})      MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// 46. FORMULA NODES — v0.4.0 BATCH
// -----------------------------------------------------------------------------
MERGE (f:Formula {id: 'f_realized_var'})
  SET f.name       = 'Realized Variance',
      f.expression = 'σ²_realized = (252/N)·Σ[ln(S_t/S_{t-1})]²',
      f.`latex`     = '\\sigma^2_{\\text{realized}} = \\frac{252}{N}\\sum_{t=1}^{N}\\left[\\ln\\frac{S_t}{S_{t-1}}\\right]^2',
      f.params      = ['S_t','S_{t-1}','N'],
      f.output      = 'annualized_realized_variance';

MERGE (f:Formula {id: 'f_var_swap_payoff'})
  SET f.name       = 'Variance Swap Payoff',
      f.expression = 'Payoff = N_vega·(σ²_realized - K²_var)',
      f.`latex`     = '\\text{Payoff} = N_{\\text{vega}}\\bigl(\\sigma^2_{\\text{realized}} - K^2_{\\text{var}}\\bigr)',
      f.params      = ['N_vega','σ²_realized','K²_var'],
      f.output      = 'swap_pnl';

MERGE (f:Formula {id: 'f_model_free_var'})
  SET f.name       = 'Model-Free Variance Replication (Carr-Madan)',
      f.expression = 'E^Q[σ²] = (2/T)·[∫₀^F P(K)/K² dK + ∫_F^∞ C(K)/K² dK]',
      f.`latex`     = '\\mathbb{E}^Q[\\sigma^2] = \\frac{2}{T}\\!\\left[\\int_0^F\\!\\frac{P(K)}{K^2}dK + \\int_F^\\infty\\!\\frac{C(K)}{K^2}dK\\right]',
      f.params      = ['T','F','P(K)','C(K)'],
      f.output      = 'risk_neutral_variance';

MERGE (f:Formula {id: 'f_breeden_litzenberger'})
  SET f.name       = 'Breeden-Litzenberger Risk-Neutral Density',
      f.expression = 'p(K) = e^(rT)·∂²C/∂K²',
      f.`latex`     = 'p(K) = e^{rT}\\frac{\\partial^2 C}{\\partial K^2}',
      f.params      = ['r','T','C','K'],
      f.output      = 'risk_neutral_pdf';

MERGE (f:Formula {id: 'f_transfer_entropy'})
  SET f.name       = 'Transfer Entropy (X→Y)',
      f.expression = 'TE(X→Y) = Σ p(y_{t+1},y_t^k,x_t^l)·log[p(y_{t+1}|y_t^k,x_t^l)/p(y_{t+1}|y_t^k)]',
      f.`latex`     = 'TE(X\\to Y)=\\sum p(y_{t+1},y_t^{(k)},x_t^{(l)})\\log\\frac{p(y_{t+1}|y_t^{(k)},x_t^{(l)})}{p(y_{t+1}|y_t^{(k)})}',
      f.params      = ['y_{t+1}','y_t^k','x_t^l','k','l'],
      f.output      = 'directed_information_flow';

MERGE (f:Formula {id: 'f_absorption_ratio'})
  SET f.name       = 'Absorption Ratio',
      f.expression = 'AR = (Σ_{k=1}^{n} σ²_{fk}) / (Σ_{i=1}^{N} σ²_{Ai})',
      f.`latex`     = 'AR = \\frac{\\sum_{k=1}^{n}\\sigma^2_{f_k}}{\\sum_{i=1}^{N}\\sigma^2_{A_i}}',
      f.params      = ['σ²_fk','σ²_Ai','n','N'],
      f.output      = 'systemic_risk_level';

MERGE (f:Formula {id: 'f_dip'})
  SET f.name       = 'Distressed Insurance Premium (DIP)',
      f.expression = 'DIP = E^Q[max(L - δ·A, 0)] where L=credit losses, δ=threshold, A=total assets',
      f.`latex`     = 'DIP = \\mathbb{E}^Q\\!\\left[\\max\\!\\left(\\sum_i L_i - \\delta \\cdot A,\\, 0\\right)\\right]',
      f.params      = ['PD_i','ρ_ij','δ','A'],
      f.output      = 'systemic_insurance_premium';

MERGE (f:Formula {id: 'f_mes'})
  SET f.name       = 'Marginal Expected Shortfall (MES)',
      f.expression = 'MES_i = E[R_i | R_m < VaR_m(α)]',
      f.`latex`     = 'MES_i = \\mathbb{E}\\bigl[R_i \\mid R_m < \\text{VaR}_m(\\alpha)\\bigr]',
      f.params      = ['R_i','R_m','α'],
      f.output      = 'tail_co_movement';

MERGE (f:Formula {id: 'f_kyles_lambda'})
  SET f.name       = "Kyle's Lambda (Price Impact)",
      f.expression = 'ΔP = λ·Q',
      f.`latex`     = '\\Delta P = \\lambda \\cdot Q',
      f.params      = ['λ','Q'],
      f.output      = 'price_impact';

MERGE (f:Formula {id: 'f_expected_shortfall'})
  SET f.name       = 'Expected Shortfall (CVaR)',
      f.expression = 'ES_α = -E[R | R < VaR_α] = -(1/(1-α))·∫_{-∞}^{VaR_α} r·f(r) dr',
      f.`latex`     = 'ES_\\alpha = -\\frac{1}{1-\\alpha}\\int_{-\\infty}^{VaR_\\alpha} r\\,f(r)\\,dr',
      f.params      = ['α','VaR_α','f(r)'],
      f.output      = 'expected_tail_loss';

MERGE (f:Formula {id: 'f_constant_dollar_gamma'})
  SET f.name       = 'Constant Dollar Gamma',
      f.expression = 'Dollar Gamma = S²·Γ/2 = constant when option weighted by 1/K²',
      f.`latex`     = '\\text{Dollar}\\;\\Gamma = \\frac{S^2 \\Gamma}{2},\\quad w_K = \\frac{1}{K^2}',
      f.params      = ['S','Γ','K'],
      f.output      = 'variance_sensitivity';

MERGE (f:Formula {id: 'f_pd_from_cds'})
  SET f.name       = 'PD from CDS Spread',
      f.expression = 'PD ≈ CDS_spread / (1 - Recovery_rate)',
      f.`latex`     = 'PD \\approx \\frac{\\text{CDS spread}}{1 - \\text{Recovery rate}}',
      f.params      = ['CDS_spread','Recovery_rate'],
      f.output      = 'probability_of_default';
// -----------------------------------------------------------------------------
// 47. CONCEPT → FORMULA RELATIONSHIPS (v0.4.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Realized Variance'}),             (f:Formula {id:'f_realized_var'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Variance Swap'}),                 (f:Formula {id:'f_var_swap_payoff'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Variance Swap'}),                 (f:Formula {id:'f_realized_var'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Model-Free Variance Replication'}),(f:Formula {id:'f_model_free_var'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Risk-Neutral PDF from Options'}), (f:Formula {id:'f_breeden_litzenberger'})MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Transfer Entropy'}),              (f:Formula {id:'f_transfer_entropy'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Absorption Ratio'}),              (f:Formula {id:'f_absorption_ratio'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Distressed Insurance Premium (DIP)'}),(f:Formula {id:'f_dip'})             MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Marginal Expected Shortfall (MES)'}),(f:Formula {id:'f_mes'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:"Kyle's Lambda"}),                 (f:Formula {id:'f_kyles_lambda'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Expected Shortfall'}),            (f:Formula {id:'f_expected_shortfall'})  MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Constant Dollar Gamma'}),         (f:Formula {id:'f_constant_dollar_gamma'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Probability of Default (PD)'}),   (f:Formula {id:'f_pd_from_cds'})         MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Spanning with Options'}),         (f:Formula {id:'f_model_free_var'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Variance Swap Strike (K_var)'}),  (f:Formula {id:'f_model_free_var'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Systemic Risk Measurement'}),     (f:Formula {id:'f_absorption_ratio'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Systemic Risk Measurement'}),     (f:Formula {id:'f_dip'})                 MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Information-Theoretic Causality'}),(f:Formula {id:'f_transfer_entropy'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'CoRisk'}),                        (f:Formula {id:'f_pd_from_cds'})         MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 48. NEW RELATIONSHIP TYPE: REPLICATES_WITH
// Links replication strategies to the instruments they use
// (Concept)-[:REPLICATES_WITH {method}]->(Concept)
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Model-Free Variance Replication'}),(b:Concept {name:'European Call Option'})
  MERGE (a)-[:REPLICATES_WITH {method:'static_strip', leg:'call_wing'}]->(b);

MATCH (a:Concept {name:'Model-Free Variance Replication'}),(b:Concept {name:'European Put Option'})
  MERGE (a)-[:REPLICATES_WITH {method:'static_strip', leg:'put_wing'}]->(b);

MATCH (a:Concept {name:'Log Contract'}),                   (b:Concept {name:'European Call Option'})
  MERGE (a)-[:REPLICATES_WITH {method:'spanning', role:'ATM_and_above'}]->(b);

MATCH (a:Concept {name:'Log Contract'}),                   (b:Concept {name:'European Put Option'})
  MERGE (a)-[:REPLICATES_WITH {method:'spanning', role:'below_ATM'}]->(b);

MATCH (a:Concept {name:'Contingent Claims Analysis (CCA)'}),(b:Concept {name:'Black-Scholes Model'})
  MERGE (a)-[:REPLICATES_WITH {method:'merton_model', role:'equity_as_call'}]->(b);


// -----------------------------------------------------------------------------
// 49. NEW RELATIONSHIP TYPE: HEDGES
// Directional hedge relationships between strategies and risk exposures
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Variance Swap'}),  (b:Concept {name:'Short Volatility Exposure'})
  MERGE (a)-[:HEDGES {direction:'long_var_swap', effectiveness:'direct'}]->(b);

MATCH (a:Concept {name:'Variance Swap'}),  (b:Concept {name:'Long Volatility Exposure'})
  MERGE (a)-[:HEDGES {direction:'short_var_swap', effectiveness:'direct'}]->(b);

MATCH (a:Concept {name:'Delta Hedging'}),  (b:Concept {name:'Vega Risk'})
  MERGE (a)-[:HEDGES {direction:'delta_neutral', effectiveness:'partial'}]->(b);

MATCH (a:Concept {name:'Put-Call Parity'}),(b:Concept {name:'Idiosyncratic Return'})
  MERGE (a)-[:HEDGES {direction:'synthetic', effectiveness:'arbitrage'}]->(b);


// -----------------------------------------------------------------------------
// 50. STRATEGY NODES — VARIANCE & VOLATILITY TRADING (v0.4.0)
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'Long Variance Swap'})
  SET s.derived_from         = 'Variance Swap',
      s.description          = 'Buy realized variance via variance swap. Profits when realized vol exceeds implied. Natural hedge for short-vol portfolios and equity long funds. Long gamma, short theta.',
      s.formula_ref          = 'f_var_swap_payoff',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_vol_threshold  = 0.20,
      s.param_maturity_days  = 30,
      s.risk_weight          = 0.7,
      s.strategy_type        = 'alpha',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Short Variance Swap (Vol Premium Harvest)'})
  SET s.derived_from           = 'Variance Risk Premium',
      s.description            = 'Sell realized variance to harvest variance risk premium (implied > realized). Structured as short variance swap. High Sharpe in calm regimes; catastrophic in crisis.',
      s.formula_ref            = 'f_var_swap_payoff',
      s.sizing_formula_ref     = 'f_sharpe',
      s.param_vega_notional_pct = 0.02,
      s.param_exit_vol_zscore  = 2.5,
      s.risk_weight            = 0.5,
      s.strategy_type          = 'alpha',
      s.status                 = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Granger Contagion Monitor'})
  SET s.derived_from           = 'Granger Causality',
      s.description            = 'Continuous Granger causality testing across ticker return series. When significant new causal links emerge (network densification signal), triggers Systemic Risk Hedge overlay.',
      s.formula_ref            = 'f_absorption_ratio',
      s.sizing_formula_ref     = 'f_contagion_prob',
      s.param_pvalue_threshold = 0.05,
      s.param_lookback_days    = 60,
      s.param_max_lag          = 4,
      s.risk_weight            = 0.95,
      s.strategy_type          = 'monitor',
      s.status                 = 'active',
      s.target_ticker      = 'XLF';


// -----------------------------------------------------------------------------
// 51. NEW STRATEGY → CONCEPT, FORMULA, REGIME RELATIONSHIPS
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'Long Variance Swap'}),                  (c:Concept {name:'Variance Swap'})           MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Long Variance Swap'}),                  (c:Concept {name:'Realized Variance'})       MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(c:Concept {name:'Variance Risk Premium'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(c:Concept {name:'Realized vs Implied Variance Spread'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (c:Concept {name:'Granger Causality'})       MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (c:Concept {name:'Absorption Ratio'})        MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (c:Concept {name:'Transfer Entropy'})        MERGE (s)-[:DERIVED_FROM]->(c);

MATCH (s:Strategy {name:'Long Variance Swap'}),                  (f:Formula {id:'f_var_swap_payoff'})         MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Long Variance Swap'}),                  (f:Formula {id:'f_realized_var'})            MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Long Variance Swap'}),                  (f:Formula {id:'f_kelly'})                   MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(f:Formula {id:'f_var_swap_payoff'})    MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(f:Formula {id:'f_sharpe'})             MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (f:Formula {id:'f_absorption_ratio'})        MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (f:Formula {id:'f_transfer_entropy'})        MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (f:Formula {id:'f_contagion_prob'})          MERGE (s)-[:HAS_FORMULA]->(f);

// Regime activations
MATCH (s:Strategy {name:'Long Variance Swap'}),                  (r:Regime {name:'HighVolatility'})    MERGE (s)-[:ACTIVATED_BY {weight:0.90}]->(r);
MATCH (s:Strategy {name:'Long Variance Swap'}),                  (r:Regime {name:'Crisis'})            MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'Long Variance Swap'}),                  (r:Regime {name:'SystemicStress'})    MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(r:Regime {name:'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(r:Regime {name:'MeanReverting'}) MERGE (s)-[:ACTIVATED_BY {weight:0.70}]->(r);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (r:Regime {name:'Trending'})          MERGE (s)-[:ACTIVATED_BY {weight:0.60}]->(r);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (r:Regime {name:'HighVolatility'})    MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (r:Regime {name:'SystemicStress'})    MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'Granger Contagion Monitor'}),           (r:Regime {name:'Crisis'})            MERGE (s)-[:ACTIVATED_BY {weight:1.00}]->(r);

// Contradictions: short variance conflicts with long variance and crisis overlays
MATCH (a:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(b:Strategy {name:'Long Variance Swap'})          MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(b:Strategy {name:'Systemic Risk Hedge'})         MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name:'Short Variance Swap (Vol Premium Harvest)'}),(b:Strategy {name:'Contagion Path Avoidance'})    MERGE (a)-[:CONTRADICTED_BY]->(b);


// -----------------------------------------------------------------------------
// 52. EXTENDED TRANSMITS_TO — FIRE SALE & ACCOUNTING MECHANICS
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Mark-to-Market Accounting'}), (b:Concept {name:'Pro-Cyclical Deleveraging'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'high', mechanism:'equity_erosion'}]->(b);

MATCH (a:Concept {name:'Pro-Cyclical Deleveraging'}), (b:Concept {name:'Fire Sale'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'extreme', mechanism:'forced_liquidation'}]->(b);

MATCH (a:Concept {name:'Cross-Asset Contagion'}),     (b:Concept {name:'Market Illiquidity'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'high', mechanism:'volume_shock'}]->(b);

MATCH (a:Concept {name:'Market Illiquidity'}),        (b:Concept {name:'Fire Sale'})
  MERGE (a)-[:TRANSMITS_TO {speed:'medium', severity:'high', mechanism:'bid_ask_widening'}]->(b);

MATCH (a:Concept {name:'Concentration Risk'}),        (b:Concept {name:'Fire Sale'})
  MERGE (a)-[:TRANSMITS_TO {speed:'fast', severity:'extreme', mechanism:'correlated_selling'}]->(b);


// -----------------------------------------------------------------------------
// 53. EXTENDED MONITORS — NEW MEASURES
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Distressed Insurance Premium (DIP)'}),(b:Concept {name:'Concentration Risk'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'CoRisk'}),                           (b:Concept {name:'Direct Counterparty Exposure'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Marginal Expected Shortfall (MES)'}), (b:Concept {name:'Too-Big-To-Fail'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Absorption Ratio'}),                  (b:Concept {name:'Systemic Risk'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Transfer Entropy'}),                  (b:Concept {name:'Contagion'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:"Kyle's Lambda"}),                     (b:Concept {name:'Market Illiquidity'})
  MERGE (a)-[:MONITORS]->(b);
MATCH (a:Concept {name:'Granger Contagion Monitor'}),         (b:Concept {name:'Network Densification'})
  MERGE (a)-[:MONITORS]->(b);


// -----------------------------------------------------------------------------
// 54. NEW AGENT QUERY PATTERNS (v0.4.0)
// -----------------------------------------------------------------------------

// Q12: Full fire sale contagion chain — accounting → market collapse
// MATCH path = (a:Concept {name:'Mark-to-Market Accounting'})-[:TRANSMITS_TO|PREREQ_OF*1..8]->(b:Concept {name:'Systemic Risk'})
// RETURN [n IN nodes(path) | n.name] AS chain,
//        [r IN relationships(path) | type(r)] AS rel_types,
//        length(path) AS depth
// ORDER BY depth ASC LIMIT 5

// Q13: Which formulas span both options and systemic risk domains?
// MATCH (c1:Concept)-[:BELONGS_TO]->(cat1:Category),
//       (c1)-[:HAS_FORMULA]->(f:Formula),
//       (c2:Concept)-[:HAS_FORMULA]->(f),
//       (c2)-[:BELONGS_TO]->(cat2:Category)
// WHERE cat1.name IN ['option_pricing','variance_swaps']
//   AND cat2.name IN ['systemic_risk','contagion']
//   AND c1 <> c2
// RETURN f.name AS formula, c1.name AS options_concept, c2.name AS risk_concept

// Q14: Find what a strategy replicates and hedges
// MATCH (s:Strategy {name: $strategy_name})
// OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c)-[:REPLICATES_WITH]->(instrument:Concept)
// OPTIONAL MATCH (s)-[:DERIVED_FROM]->(c2)-[:HEDGES]->(exposure:Concept)
// RETURN s.name, collect(DISTINCT instrument.name) AS replicates_with, collect(DISTINCT exposure.name) AS hedges

// Q15: Granger causality monitor → triggered regime + strategies
// MATCH (monitor:Strategy {name:'Granger Contagion Monitor'})-[:ACTIVATED_BY]->(r:Regime),
//       (overlay:Strategy {strategy_type:'overlay'})-[:ACTIVATED_BY]->(r)
// RETURN r.name AS regime, monitor.name, collect(overlay.name) AS overlays_triggered

// =============================================================================
// END v0.4.0
// -----------------------------------------------------------------------------
// KG STATS AFTER v0.4.0 LOAD:
//   Concept nodes      : 140+ (93 + 46 new + 1 bridge = 140)
//   Category nodes     : 36   (29 + 7 new)
//   Formula nodes      : 45   (33 + 12 new)
//   Strategy nodes     : 13   (10 + 3 new)
//   Regime nodes       : 7    (unchanged)
//   Ticker nodes       : 10   (unchanged)
//   PREREQ_OF edges    : ~155 (~95 + ~60 new)
//   TRANSMITS_TO edges : 11   (6 + 5 new)
//   MONITORS edges     : 17   (10 + 7 new)
//   ACTIVATED_BY edges : 33   (24 + 9 new)
//   CONTRADICTED_BY    : 8    (5 + 3 new)
//   HAS_FORMULA edges  : ~76  (~57 + ~19 new)
//   REPLICATES_WITH    : 5    (new relationship type)
//   HEDGES             : 4    (new relationship type)
// Total relationship types: 12
//   PREREQ_OF, BELONGS_TO, HAS_FORMULA, DERIVED_FROM,
//   ACTIVATED_BY, CONTRADICTED_BY, TRANSMITS_TO, MONITORS,
//   REPLICATES_WITH, HEDGES,
//   CORRELATED_WITH (runtime), HAS_SIGNAL (runtime)
// Concept domains covered:
//   Options & Vol | Factor Investing | Estimation | Systemic Risk |
//   Network Theory | Shadow Banking | Fire Sale Mechanics |
//   Contingent Claims | Granger Causality | Information Theory |
//   Variance Swaps | OTC Derivatives | Replication Theory
// =============================================================================


// =============================================================================
// v0.4.0 ADDITIONS
// Sources:
//   - "Variance Swaps: Spanning with Options" (WQU M2L2, Hilpisch / Demeterfi)
//   - "Jumping for Better Volatility Estimation" (WQU M2L3, Spadafora et al.)
// New domains: Levy processes, jump models, order statistics, volatility
//   estimation, option spanning mechanics, implicit vol exposure taxonomy
// -----------------------------------------------------------------------------
// New concepts  : 26
// New categories: 2  (jump_models, order_statistics)
// New formulas  : 8
// New strategies: 1  (Jump-Filtered Vol Trading)
// New rel types : GENERALIZES_TO (process hierarchy)
// =============================================================================


// -----------------------------------------------------------------------------
// 39. SCHEMA VERSION BUMP
// -----------------------------------------------------------------------------
// Schema version: 0.4.0
// Changelog:
//   0.4.0 — Levy/Ito/Wiener process hierarchy, Poisson jump process,
//            jump-diffusion SDE, OS volatility estimator (Spadafora),
//            order statistics & incomplete beta function, jump classification
//            algorithm, variance swap spanning mechanics (Hilpisch/Demeterfi),
//            option strip scaling, constant-dollar-gamma weighting, implicit
//            short vol taxonomy (merger arb, benchmarking, equity funds).


// -----------------------------------------------------------------------------
// 40. NEW CATEGORY NODES
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'jump_models',      display: 'Jump & Levy Models'});
MERGE (:Category {name: 'order_statistics', display: 'Order Statistics'});


// -----------------------------------------------------------------------------
// 41. CONCEPT NODES — PROCESS HIERARCHY
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Wiener Process'})
  SET c.definition   = 'Continuous-time stochastic process W(t) with independent Gaussian increments: W(t)-W(s) ~ N(0,t-s). Foundation of Black-Scholes and Ito calculus.',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';

MERGE (c:Concept {name: 'Ito Process'})
  SET c.definition   = 'Stochastic process dX = μ(X,t)dt + σ(X,t)dW. Drift plus Brownian diffusion. Basis of Black-Scholes. Assumes continuous, smooth price paths with no jumps.',
      c.category     = 'stochastic_processes',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';

MERGE (c:Concept {name: 'Levy Process'})
  SET c.definition   = 'Generalisation of the Ito process adding a jump component J(t): dY = σdW + dJ. Captures discontinuous price moves. Encompasses Brownian motion (dJ=0) as a special case.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3; Spadafora et al. 2018';

MERGE (c:Concept {name: 'Jump Process (Poisson)'})
  SET c.definition   = 'Compound Poisson process J(t) = Σ Y_i where jumps arrive at rate λ and have random sizes Y_i. Superimposed on Brownian motion in Levy models.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';

MERGE (c:Concept {name: 'Jump-Diffusion Log Return SDE'})
  SET c.definition   = 'dY_t = σ_t·dW_t + dJ_t = dY_t^c + dJ_t. Decomposes log return into continuous volatility component dY^c and jump component dJ. Spadafora et al. formulation.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. 2018';

MERGE (c:Concept {name: 'Continuous Volatility Component'})
  SET c.definition   = 'The dY^c = σ_t·dW_t term in the jump-diffusion SDE. Represents smooth Brownian variance. The OS estimator targets this component, filtering out jump observations.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';


// -----------------------------------------------------------------------------
// 42. CONCEPT NODES — ORDER STATISTICS & OS ESTIMATOR
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Order Statistics'})
  SET c.definition   = 'The sorted values X_(1) ≤ X_(2) ≤ ... ≤ X_(n) of a sample. The k-th order statistic X_(k) has a known CDF derived from the original distribution. Used to identify outliers and jumps.',
      c.category     = 'order_statistics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3; Rundel 2012';

MERGE (c:Concept {name: 'Order Statistic CDF'})
  SET c.definition   = 'CDF of k-th order statistic of n iid standard normals expressed via incomplete beta function: F_(k)(x) = I_{Φ(x)}(k, n-k+1). Enables probability that an observation belongs to reference distribution.',
      c.category     = 'order_statistics',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. 2018';

MERGE (c:Concept {name: 'Incomplete Beta Function'})
  SET c.definition   = 'I_x(a,b) = B(x;a,b)/B(a,b). Regularised incomplete beta function. Used to compute order statistic CDFs for Gaussian reference distribution in jump classification.',
      c.category     = 'order_statistics',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. 2018';

MERGE (c:Concept {name: 'Gaussian Reference Distribution'})
  SET c.definition   = 'Assumed null distribution for continuous log returns in jump-diffusion models. Observations inconsistent with this distribution at tolerance p are classified as jumps.',
      c.category     = 'order_statistics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';

MERGE (c:Concept {name: 'Jump Threshold (Theta)'})
  SET c.definition   = 'θ̂ = θ(p, n′, k) · ŝ. Scaled standard deviation threshold above which an observation is classified as a jump. Derived from order statistic CDF at tolerance p.',
      c.category     = 'order_statistics',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. 2018';

MERGE (c:Concept {name: 'Jump Classification'})
  SET c.definition   = 'Binary decision: if |log return| > θ̂, the observation is classified as a jump and excluded from Gaussian volatility estimation. Applied iteratively via the OS algorithm.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';

MERGE (c:Concept {name: 'OS Volatility Estimator'})
  SET c.definition   = 'Algorithm by Spadafora et al. estimating continuous volatility σ_t from log returns by iteratively removing jump observations using order statistic thresholds. Returns Gaussian-consistent volatility.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. 2018';

MERGE (c:Concept {name: 'Integrated Variance'})
  SET c.definition   = 'E[∫₀ᵀ σ²(S_t)dt]. Expected quadratic variation of the continuous price process over [0,T]. Target of variance swap payoff; related to log contract via E[∫σ²dt] = -2E[log(S_T/F)].',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Hilpisch (WQU M2L2)';

MERGE (c:Concept {name: 'Heteroskedasticity (Time-Varying Vol)'})
  SET c.definition   = 'Property of a process where variance σ²_t changes over time. The extended OS estimator (Spadafora et al.) accommodates this by allowing the volatility term to evolve.',
      c.category     = 'jump_models',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M2L3';


// -----------------------------------------------------------------------------
// 43. CONCEPT NODES — VARIANCE SWAP SPANNING MECHANICS
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Twice-Differentiable Payoff Spanning'})
  SET c.definition   = 'Any payoff g(S_T) that is twice continuously differentiable can be replicated exactly by a portfolio of European puts (strikes 0 to F) and calls (strikes F to ∞). Hilpisch/Breeden-Litzenberger result.',
      c.category     = 'derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch WQU M2L2; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Payout Function Replication'})
  SET c.definition   = 'E_t[g(S_T)|S_t] = ∫₀^F g(K)·∂²P/∂K² dK + ∫_F^∞ g(K)·∂²C/∂K² dK. General spanning formula splitting at forward price F using put and call option strips.',
      c.category     = 'derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch WQU M2L2';

MERGE (c:Concept {name: 'Option Strip Scaling'})
  SET c.definition   = 'Weighting each option in the replication strip by 1/K² to achieve constant dollar gamma across strikes. Ensures variance swap has equal vol exposure at all price levels.',
      c.category     = 'derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Hilpisch WQU M2L2; Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Dollar Gamma Constant Strike Weighting'})
  SET c.definition   = 'Dollar gamma = ½·S²·Γ. Weighting options by 1/K² makes dollar gamma constant across strikes, ensuring variance swap payoff is independent of underlying price level.',
      c.category     = 'derivatives',
      c.difficulty   = 'advanced',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Collateralization (OTC Margin)'})
  SET c.definition   = 'Credit risk mitigation in OTC derivatives via initial margin (upfront collateral) and variation margin (daily mark-to-market settlement). Governed by ISDA/CSA. Reduces counterparty credit risk from accumulating unrealised losses.',
      c.category     = 'risk_management',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M2L1';


// -----------------------------------------------------------------------------
// 44. CONCEPT NODES — IMPLICIT VOLATILITY EXPOSURE TAXONOMY
// (Demeterfi et al. classification of naturally short-vol market participants)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Implicit Short Volatility'})
  SET c.definition   = 'Structural short volatility exposure embedded in a portfolio or strategy, not from explicit derivatives positions. Examples: equity funds (negative equity-vol correlation), merger arb, benchmarked managers.',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Merger Arbitrage Volatility Risk'})
  SET c.definition   = 'Risk arbitrageurs are implicitly short volatility: if market volatility spikes, merger deals break and spreads widen, causing losses. Higher vol → higher deal-break probability.',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';

MERGE (c:Concept {name: 'Benchmarking Tracking Error Vol Risk'})
  SET c.definition   = 'Portfolio managers benchmarked to an index incur higher tracking error and rebalancing costs in volatile markets. Higher vol → higher transaction costs → performance drag.',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Pricer',
      c.source       = 'Demeterfi et al. 1999';


// -----------------------------------------------------------------------------
// 45. NEW CONCEPT → CATEGORY RELATIONSHIPS (v0.4.0)
// Scoped by menu_context = 'Model' or new categories
// -----------------------------------------------------------------------------

MATCH (c:Concept), (cat:Category)
WHERE c.category = cat.name
  AND c.menu_context = 'Model'
  AND c.source CONTAINS 'M2L'
MERGE (c)-[:BELONGS_TO]->(cat);

// Implicit vol taxonomy — scoped match
MATCH (c:Concept {name:'Implicit Short Volatility'}),         (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Merger Arbitrage Volatility Risk'}),  (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Benchmarking Tracking Error Vol Risk'}),(cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Collateralization (OTC Margin)'}),    (cat:Category {name:'risk_management'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Twice-Differentiable Payoff Spanning'}),(cat:Category {name:'derivatives'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Payout Function Replication'}),       (cat:Category {name:'derivatives'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Option Strip Scaling'}),              (cat:Category {name:'derivatives'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Dollar Gamma Constant Strike Weighting'}),(cat:Category {name:'derivatives'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Integrated Variance'}),               (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// 46. NEW RELATIONSHIP TYPE: GENERALIZES_TO
// Captures the process hierarchy: Wiener ⊂ Ito ⊂ Levy
// Direction: the simpler process GENERALIZES_TO the richer one
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Wiener Process'}),   (b:Concept {name:'Ito Process'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_drift_and_state_dependence'}]->(b);

MATCH (a:Concept {name:'Ito Process'}),      (b:Concept {name:'Levy Process'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_jump_component'}]->(b);

MATCH (a:Concept {name:'Geometric Brownian Motion'}), (b:Concept {name:'Ito Process'})
  MERGE (a)-[:GENERALIZES_TO {by:'constant_coeff_special_case'}]->(b);

MATCH (a:Concept {name:'Jump Process (Poisson)'}), (b:Concept {name:'Levy Process'})
  MERGE (a)-[:GENERALIZES_TO {by:'jump_component_of_levy'}]->(b);

MATCH (a:Concept {name:'Jump Diffusion'}),   (b:Concept {name:'Levy Process'})
  MERGE (a)-[:GENERALIZES_TO {by:'ito_plus_poisson_jumps'}]->(b);


// -----------------------------------------------------------------------------
// 47. PREREQUISITE RELATIONSHIPS — PROCESS HIERARCHY & JUMP MODELS
// -----------------------------------------------------------------------------

// Process hierarchy prerequisites
MATCH (a:Concept {name:'Geometric Brownian Motion'}),(b:Concept {name:'Wiener Process'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Wiener Process'}),           (b:Concept {name:'Ito Process'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Ito Process'}),              (b:Concept {name:'Levy Process'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Diffusion'}),           (b:Concept {name:'Levy Process'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Process (Poisson)'}),   (b:Concept {name:'Levy Process'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Levy Process'}),             (b:Concept {name:'Jump-Diffusion Log Return SDE'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Process (Poisson)'}),   (b:Concept {name:'Jump-Diffusion Log Return SDE'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Ito Process'}),              (b:Concept {name:'Continuous Volatility Component'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump-Diffusion Log Return SDE'}),(b:Concept {name:'Continuous Volatility Component'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Levy Process'}),             (b:Concept {name:'Heteroskedasticity (Time-Varying Vol)'}) MERGE (a)-[:PREREQ_OF]->(b);

// Jump model prerequisites → Variance Swap
MATCH (a:Concept {name:'Levy Process'}),             (b:Concept {name:'Variance Swap'})     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Integrated Variance'}),      (b:Concept {name:'Variance Swap'})     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Continuous Volatility Component'}),(b:Concept {name:'Realized Variance'}) MERGE (a)-[:PREREQ_OF]->(b);

// Order statistics chain
MATCH (a:Concept {name:'Order Statistics'}),         (b:Concept {name:'Order Statistic CDF'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Order Statistic CDF'}),      (b:Concept {name:'Incomplete Beta Function'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Incomplete Beta Function'}), (b:Concept {name:'Jump Threshold (Theta)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gaussian Reference Distribution'}),(b:Concept {name:'Jump Threshold (Theta)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Threshold (Theta)'}),   (b:Concept {name:'Jump Classification'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Classification'}),      (b:Concept {name:'OS Volatility Estimator'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Order Statistics'}),         (b:Concept {name:'OS Volatility Estimator'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'OS Volatility Estimator'}),  (b:Concept {name:'Integrated Variance'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Heteroskedasticity (Time-Varying Vol)'}),(b:Concept {name:'OS Volatility Estimator'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump-Diffusion Log Return SDE'}),(b:Concept {name:'OS Volatility Estimator'}) MERGE (a)-[:PREREQ_OF]->(b);

// Spanning mechanics prerequisites
MATCH (a:Concept {name:'Risk-Neutral Pricing'}),     (b:Concept {name:'Twice-Differentiable Payoff Spanning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'State Prices (Arrow-Debreu)'}),(b:Concept {name:'Twice-Differentiable Payoff Spanning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Risk-Neutral PDF from Options'}),(b:Concept {name:'Twice-Differentiable Payoff Spanning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Twice-Differentiable Payoff Spanning'}),(b:Concept {name:'Payout Function Replication'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Payout Function Replication'}),(b:Concept {name:'Option Strip Scaling'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Constant Dollar Gamma'}),    (b:Concept {name:'Dollar Gamma Constant Strike Weighting'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Option Strip Scaling'}),     (b:Concept {name:'Dollar Gamma Constant Strike Weighting'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Dollar Gamma Constant Strike Weighting'}),(b:Concept {name:'Model-Free Variance Replication'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Log Contract'}),             (b:Concept {name:'Integrated Variance'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Log Contract'}),             (b:Concept {name:'Payout Function Replication'}) MERGE (a)-[:PREREQ_OF]->(b);

// Implicit short vol taxonomy
MATCH (a:Concept {name:'Variance Swap'}),            (b:Concept {name:'Implicit Short Volatility'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implicit Short Volatility'}),(b:Concept {name:'Merger Arbitrage Volatility Risk'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Implicit Short Volatility'}),(b:Concept {name:'Benchmarking Tracking Error Vol Risk'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Low Volatility Anomaly'}),   (b:Concept {name:'Implicit Short Volatility'}) MERGE (a)-[:PREREQ_OF]->(b);

// OTC collateral
MATCH (a:Concept {name:'Variation Margin (OTC)'}),   (b:Concept {name:'Collateralization (OTC Margin)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Initial Margin (OTC)'}),     (b:Concept {name:'Collateralization (OTC Margin)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Collateralization (OTC Margin)'}),(b:Concept {name:'Variance Swap'}) MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain: jump classification → VaR → systemic risk
MATCH (a:Concept {name:'Jump Classification'}),      (b:Concept {name:'Jump Diffusion'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'OS Volatility Estimator'}),  (b:Concept {name:'Realized Variance'}) MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// 48. FORMULA NODES — PROCESS & JUMP BATCH
// -----------------------------------------------------------------------------
MERGE (f:Formula {id: 'f_levy_sde'})
  SET f.name       = 'Levy Process Log Return SDE',
      f.expression = 'dY_t = σ_t·dW_t + dJ_t',
      f.`latex`     = 'dY_t = \\sigma_t\\,dW_t + dJ_t = dY_t^c + dJ_t',
      f.params      = ['σ_t','dW_t','dJ_t'],
      f.output      = 'log_return_increment';

MERGE (f:Formula {id: 'f_integrated_var'})
  SET f.name       = 'Integrated Variance = Log Contract Expectation',
      f.expression = 'E[∫₀ᵀ σ²(S_t)dt] = -2E[log(S_T/F)]',
      f.`latex`     = '\\mathbb{E}\\!\\left[\\int_0^T\\sigma^2(S_t)\\,dt\\right] = -2\\,\\mathbb{E}\\!\\left[\\log\\frac{S_T}{F}\\right]',
      f.params      = ['σ_t','S_T','F','T'],
      f.output      = 'integrated_variance';

MERGE (f:Formula {id: 'f_spanning'})
  SET f.name       = 'Twice-Differentiable Payoff Spanning (Hilpisch)',
      f.expression = 'E_t[g(S_T)] = ∫₀^F g(K)·∂²P/∂K² dK + ∫_F^∞ g(K)·∂²C/∂K² dK',
      f.`latex`     = '\\mathbb{E}_t[g(S_T)] = \\int_0^F g(K)\\frac{\\partial^2 P}{\\partial K^2}dK + \\int_F^\\infty g(K)\\frac{\\partial^2 C}{\\partial K^2}dK',
      f.params      = ['g','P','C','K','F'],
      f.output      = 'replicated_expected_payoff';

MERGE (f:Formula {id: 'f_rnpdf'})
  SET f.name       = 'Risk-Neutral PDF from Option Prices (Breeden-Litzenberger)',
      f.expression = 'p(S_T,T; S_t,t) = ∂²P/∂K² |_{S_T=K} = ∂²C/∂K² |_{S_T=K}',
      f.`latex`     = 'p(S_T,T;S_t,t)=\\left.\\frac{\\partial^2 P(S_t,K,T)}{\\partial K^2}\\right|_{S_T=K}=\\left.\\frac{\\partial^2 C(S_t,K,T)}{\\partial K^2}\\right|_{S_T=K}',
      f.params      = ['P','C','K'],
      f.output      = 'risk_neutral_pdf';

MERGE (f:Formula {id: 'f_os_threshold'})
  SET f.name       = 'OS Jump Threshold (Spadafora)',
      f.expression = 'θ̂ = θ(p, n′, k) · ŝ',
      f.`latex`     = '\\hat{\\theta} = \\theta(p,n^\\prime,k)\\cdot\\hat{s}',
      f.params      = ['p','n_prime','k','s_hat'],
      f.output      = 'jump_threshold';

MERGE (f:Formula {id: 'f_order_stat_cdf'})
  SET f.name       = 'k-th Order Statistic CDF (Normal)',
      f.expression = 'F_(k)(x) = I_{Φ(x)}(k, n-k+1)',
      f.`latex`     = 'F_{(k)}(x) = I_{\\Phi(x)}(k,\\, n-k+1)',
      f.params      = ['x','k','n'],
      f.output      = 'order_stat_probability';

MERGE (f:Formula {id: 'f_log_contract'})
  SET f.name       = 'Log Contract Decomposition',
      f.expression = 'log(S_T/F) = ∫₀ᵀ dS_t/S_t - ∫₀ᵀ σ²(S_t)/2 dt',
      f.`latex`     = '\\log\\frac{S_T}{F}=\\int_0^T\\frac{dS_t}{S_t}-\\int_0^T\\frac{\\sigma^2(S_t)}{2}\\,dt',
      f.params      = ['S_T','F','σ_t'],
      f.output      = 'log_return_decomposition';

MERGE (f:Formula {id: 'f_dollar_gamma'})
  SET f.name       = 'Dollar Gamma',
      f.expression = 'Dollar Gamma = ½·S²·Γ = ½·S²·∂²V/∂S²',
      f.`latex`     = '\\text{Dollar Gamma} = \\tfrac{1}{2}S^2\\Gamma = \\tfrac{1}{2}S^2\\frac{\\partial^2 V}{\\partial S^2}',
      f.params      = ['S','Γ'],
      f.output      = 'dollar_gamma';

// -----------------------------------------------------------------------------
// 49. CONCEPT → FORMULA RELATIONSHIPS (v0.4.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Levy Process'}),                    (f:Formula {id:'f_levy_sde'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Jump-Diffusion Log Return SDE'}),   (f:Formula {id:'f_levy_sde'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Integrated Variance'}),             (f:Formula {id:'f_integrated_var'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Log Contract'}),                    (f:Formula {id:'f_integrated_var'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Log Contract'}),                    (f:Formula {id:'f_log_contract'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Twice-Differentiable Payoff Spanning'}),(f:Formula {id:'f_spanning'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Payout Function Replication'}),     (f:Formula {id:'f_spanning'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Risk-Neutral PDF from Options'}),   (f:Formula {id:'f_rnpdf'})             MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Option Strip Scaling'}),            (f:Formula {id:'f_rnpdf'})             MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Dollar Gamma Constant Strike Weighting'}),(f:Formula {id:'f_dollar_gamma'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Constant Dollar Gamma'}),           (f:Formula {id:'f_dollar_gamma'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'OS Volatility Estimator'}),         (f:Formula {id:'f_os_threshold'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Jump Threshold (Theta)'}),          (f:Formula {id:'f_os_threshold'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Order Statistic CDF'}),             (f:Formula {id:'f_order_stat_cdf'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Incomplete Beta Function'}),        (f:Formula {id:'f_order_stat_cdf'})    MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Model-Free Variance Replication'}), (f:Formula {id:'f_spanning'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Variance Swap'}),                   (f:Formula {id:'f_integrated_var'})    MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 50. STRATEGY NODE — JUMP-FILTERED VOLATILITY TRADING
// Agent uses OS estimator output to trade variance swaps with jump-adjusted strike
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'Jump-Filtered Vol Trading'})
  SET s.derived_from         = 'OS Volatility Estimator',
      s.description          = 'Enter long/short variance swap when OS-estimated continuous vol diverges significantly from implied vol (variance swap strike K_var). Jump-filters realized vol before comparing to implied to avoid mis-sizing due to jump noise.',
      s.formula_ref          = 'f_os_threshold',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_vol_diff_entry = 0.03,
      s.param_jump_tol       = 0.01,
      s.risk_weight          = 0.65,
      s.strategy_type        = 'alpha',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (c:Concept {name:'OS Volatility Estimator'})   MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (c:Concept {name:'Variance Swap'})             MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (f:Formula {id:'f_os_threshold'})              MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (f:Formula {id:'f_realized_var'})              MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (f:Formula {id:'f_var_swap_payoff'})           MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (f:Formula {id:'f_kelly'})                     MERGE (s)-[:HAS_FORMULA]->(f);

MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (r:Regime {name:'HighVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (r:Regime {name:'Crisis'})          MERGE (s)-[:ACTIVATED_BY {weight:0.70}]->(r);
MATCH (s:Strategy {name:'Jump-Filtered Vol Trading'}), (r:Regime {name:'Recovery'})        MERGE (s)-[:ACTIVATED_BY {weight:0.60}]->(r);

// Jump-filtered vol does not conflict with systemic risk overlays (complementary)
// Does conflict with naive vol mean reversion (which doesn't filter jumps)
MATCH (a:Strategy {name:'Jump-Filtered Vol Trading'}), (b:Strategy {name:'Volatility Mean Reversion'})
  MERGE (a)-[:CONTRADICTED_BY]->(b);


// -----------------------------------------------------------------------------
// 51. NEW AGENT QUERY PATTERNS (v0.4.0)
// -----------------------------------------------------------------------------

// Q12: Full process hierarchy from Wiener to Levy
// MATCH path = (w:Concept {name:'Wiener Process'})-[:GENERALIZES_TO*1..4]->(target:Concept)
// RETURN [n IN nodes(path) | n.name] AS hierarchy, length(path) AS depth
// ORDER BY depth

// Q13: Jump model chain — from SDE to estimator to strategy
// MATCH path = (sde:Concept {name:'Jump-Diffusion Log Return SDE'})-[:PREREQ_OF*1..5]->(s:Strategy)
// RETURN [n IN nodes(path) | n.name] AS chain

// Q14: Spanning replication chain for variance swap
// MATCH path = (a:Concept {name:'Twice-Differentiable Payoff Spanning'})-[:PREREQ_OF*1..4]->(v:Concept {name:'Variance Swap'})
// RETURN [n IN nodes(path) | n.name] AS replication_chain

// Q15: Implicit short vol exposure — who needs to hedge?
// MATCH (short:Concept {name:'Implicit Short Volatility'})-[:PREREQ_OF]->(risk:Concept)
// RETURN risk.name AS implicit_vol_risk, risk.definition AS description

// =============================================================================
// END v0.4.0
// -----------------------------------------------------------------------------
// KG STATS AFTER v0.4.0 LOAD:
//   Concept nodes      : 119  (93 + 26 new)
//   Category nodes     : 31   (29 + 2 new)
//   Formula nodes      : 53   (45 + 8 new)
//   Strategy nodes     : 14   (13 + 1 new)
//   Regime nodes       : 7    (unchanged)
//   Ticker nodes       : 10   (unchanged)
//   PREREQ_OF edges    : ~145 (~95 + ~50 new)
//   GENERALIZES_TO edges: 5   (new relationship type — process hierarchy)
//   ACTIVATED_BY edges : 27   (24 + 3 new)
//   CONTRADICTED_BY    : 9    (8 + 1 new)
//   HAS_FORMULA edges  : ~74  (~57 + ~17 new)
//   TRANSMITS_TO edges : 6    (unchanged)
//   MONITORS edges     : 10   (unchanged)
//   REPLICATES_WITH    : 5    (unchanged)
//   HEDGES             : 4    (unchanged)
//   GENERALIZES_TO     : 5    (new)
// Total relationship types: 13
//   PREREQ_OF, BELONGS_TO, HAS_FORMULA, DERIVED_FROM,
//   ACTIVATED_BY, CONTRADICTED_BY, TRANSMITS_TO, MONITORS,
//   REPLICATES_WITH, HEDGES, GENERALIZES_TO,
//   CORRELATED_WITH (runtime), HAS_SIGNAL (runtime)
// Concept domains covered:
//   Options & Vol | Factor Investing | Estimation | Systemic Risk |
//   Network Theory | Shadow Banking | Fire Sale Mechanics |
//   Contingent Claims | Granger Causality | Information Theory |
//   Variance Swaps | OTC Derivatives | Replication Theory |
//   Levy & Jump Models | Order Statistics | OS Volatility Estimation |
//   Spanning Mechanics | Implicit Vol Taxonomy
// =============================================================================


// =============================================================================
// v0.5.0 ADDITIONS
// Sources:
//   - "Order Statistics Volatility Estimator in Action" (WQU M2L4, Spadafora)
//   - "DeepVaR: VaR Meets Long-Short Term Memory" (WQU M3L1, Fatouros et al.)
//   - "DeepVaR: The Python Implementation" (WQU M3L2)
//   - "Forecasting Volatility with Transformers" (WQU M3L3, Ramos-Perez et al.)
// New domains: OS algorithm internals, deep learning for VaR (RNN/LSTM/GRU),
//   transformer architecture, probabilistic forecasting, VaR backtesting metrics
// -----------------------------------------------------------------------------
// New concepts  : 36
// New categories: 3  (deep_learning, var_backtesting, probabilistic_forecasting)
// New formulas  : 9
// New strategies: 2  (DeepVaR Portfolio Risk, Transformer Vol Forecast)
// New rel type  : TRAINED_BY, EVALUATED_BY
// =============================================================================


// -----------------------------------------------------------------------------
// 52. SCHEMA VERSION BUMP
// -----------------------------------------------------------------------------
// Schema version: 0.5.0
// Changelog:
//   0.5.0 — OS algorithm internals (local_vol, _thrLocalVol, local_vol_order_stats,
//            _getkJumpProb, _kSmallestCDF, convergence), RNN/GRU/LSTM hierarchy,
//            DeepAR/DeepVaR probabilistic VaR, VaR backtesting loss functions
//            (hit, quadratic, smooth, tick, firm), Christoffersen/DQ tests,
//            transformer architecture (attention, MHSA, encoder-decoder, FFN,
//            positional encoding), Multi-Transformer for volatility forecasting.


// -----------------------------------------------------------------------------
// 53. NEW CATEGORY NODES
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'deep_learning',              display: 'Deep Learning'});
MERGE (:Category {name: 'var_backtesting',            display: 'VaR Backtesting'});
MERGE (:Category {name: 'probabilistic_forecasting',  display: 'Probabilistic Forecasting'});


// -----------------------------------------------------------------------------
// 54. CONCEPT NODES — OS ALGORITHM INTERNALS (M2L4)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Local Volatility (Rolling Window)'})
  SET c.definition   = 'Rolling standard deviation of all returns within bandwidth window, agnostic to jumps. Naive baseline: local_volatility function in Spadafora repo. Overestimates true continuous vol when jumps present.',
      c.category     = 'jump_models',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';

MERGE (c:Concept {name: 'Theoretical Volatility (Jump-Filtered)'})
  SET c.definition   = 'Volatility computed from non-jump returns only. Multiplies jump returns by zero, continuous by one, then computes std. Corresponds to _thrLocalVol (Algorithm 1, Spadafora).',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';

MERGE (c:Concept {name: 'Local Vol with Order Statistics'})
  SET c.definition   = 'Algorithm 2 (Spadafora): iteratively identifies jumps via _getkJumpProb and recomputes continuous vol via _thrLocalVol until convergence. Full local_vol_order_stats function.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';

MERGE (c:Concept {name: 'Jump Indicator Array'})
  SET c.definition   = 'Binary boolean array ju where 1=jump, 0=continuous return. Initialised to all zeros. Updated iteratively by _getkJumpProb. Convergence when ju unchanged between iterations.',
      c.category     = 'jump_models',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';

MERGE (c:Concept {name: 'kSmallestCDF'})
  SET c.definition   = 'Function computing P(k-th order statistic is not a jump) via scipy.special.betainc. Arguments: x=normalized return, k=order statistic rank, n=non-jump count. Decision boundary for classification.',
      c.category     = 'order_statistics',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';

MERGE (c:Concept {name: 'Convergence Criterion (OS Algorithm)'})
  SET c.definition   = 'Loop termination condition: np.sum(ju_old == ju) == len(returns). Jump array unchanged between iterations means stable classification reached. maxiter=100 hard cap.',
      c.category     = 'jump_models',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';

MERGE (c:Concept {name: 'Return Renormalization'})
  SET c.definition   = 'Division of log returns by their local volatility before order statistic comparison. Standardises returns to unit-variance Gaussian reference for jump probability calculation.',
      c.category     = 'jump_models',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'Spadafora et al. WQU M2L4';


// -----------------------------------------------------------------------------
// 55. CONCEPT NODES — RNN HIERARCHY & DEEPVAR (M3L1, M3L2)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Recurrent Neural Network (RNN)'})
  SET c.definition   = 'Neural network with temporal feedback: each hidden cell receives current input plus its own previous output. Unrolled across time steps. Three weight sets per cell: self, cross-hidden, output.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L1';

MERGE (c:Concept {name: 'Gated Recurrent Unit (GRU)'})
  SET c.definition   = 'RNN extension with two gates: reset gate (short-term dependency capture) and update gate (long-term dependency, controls how much new state copies old state). More parameter-efficient than LSTM.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L1';

MERGE (c:Concept {name: 'Long Short-Term Memory (LSTM)'})
  SET c.definition   = 'RNN with four gates: input gate (new info storage), forget gate (old info removal), output gate (hidden state update), memory cell (long-range storage). Core of DeepVaR. Longer training time than GRU.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L1';

MERGE (c:Concept {name: 'Probabilistic Forecasting'})
  SET c.definition   = 'Predicting a full probability distribution over future values rather than a point estimate. Required for VaR: need quantile extraction at alpha=0.95/0.99. GluonTS framework.',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L1; Salinas et al. 2017';

MERGE (c:Concept {name: 'DeepAR'})
  SET c.definition   = 'Autoregressive RNN model (Salinas et al. 2017) producing probabilistic forecasts by learning conditional distribution p(z_t|theta,h_t). Maximises log-likelihood L=Σlog(l(z|θ(h))). Adam optimizer.',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Salinas et al. 2017; Fatouros et al. 2022';

MERGE (c:Concept {name: 'DeepVaR'})
  SET c.definition   = 'Portfolio VaR framework combining DeepAR probabilistic forecasting with correlation-weighted aggregation. VaR_p = sqrt(V*R*V^T) where V=weighted per-instrument VaRs, R=correlation matrix.',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Fatouros et al. 2022';

MERGE (c:Concept {name: 'GluonTS'})
  SET c.definition   = 'AWS time-series forecasting toolkit. Probabilistic focus. Implements DeepAR via DeepAREstimator. Key params: freq, prediction_length, context_length, num_layers, num_cells, cell_type, dropout_rate.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L2';

MERGE (c:Concept {name: 'Adam Optimizer'})
  SET c.definition   = 'Adaptive gradient descent combining momentum and RMSProp. Default in DeepAR/DeepVaR training. Updates model parameters to maximise log-likelihood of training data.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L2';

MERGE (c:Concept {name: 'Student-t Output Distribution'})
  SET c.definition   = 'Default likelihood distribution in DeepAR (StudentTOutput). Heavy tails appropriate for financial returns. Parameters mu, sigma, nu learned by LSTM. Captures fat-tail VaR risk.',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L2';

MERGE (c:Concept {name: 'Portfolio VaR (DeepVaR)'})
  SET c.definition   = 'VaR_p = sqrt(V*R*V^T). V = vector of weighted per-instrument VaR estimates. R = asset correlation matrix. For long positions: VaR uses low percentile of forecast distribution; short: high percentile.',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Fatouros et al. 2022';

MERGE (c:Concept {name: 'Rolling Correlation (125-day)'})
  SET c.definition   = 'Dynamic correlation estimate using 125-day rolling window. Captures non-stationarity of correlations. Improvement over single static correlation in portfolio VaR, especially during turmoil.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L2';


// -----------------------------------------------------------------------------
// 56. CONCEPT NODES — VAR BACKTESTING METRICS (M3L1)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'VaR Backtesting'})
  SET c.definition   = 'Systematic evaluation of VaR model accuracy against historical or simulated realizations. Key: hit rate, loss functions, statistical validity tests (Christoffersen, Dynamic Quantile).',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Fatouros et al. 2022; Bayer backtest.py';

MERGE (c:Concept {name: 'Hit Variable (VaR)'})
  SET c.definition   = 'I_t = 1{actual_t < VaR_t}. Binary: 1 if actual loss exceeds VaR threshold (exceedance/violation). Expected mean = 1-alpha (e.g., 5% for 95% VaR). Also called violation indicator.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'Fatouros et al. 2022';

MERGE (c:Concept {name: 'Quadratic Loss (VaR)'})
  SET c.definition   = 'L_quad = hit_series*(1+(actual-forecast)^2). Penalizes exceedances quadratically in magnitude. Zero contribution when loss does not exceed VaR threshold.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Fatouros et al. 2022 eq.11';

MERGE (c:Concept {name: 'Smooth Loss (VaR)'})
  SET c.definition   = 'L_smooth = (alpha-(1+exp(delta*(actual-forecast)))^-1)*(actual-forecast). Differentiable approximation to tick loss (delta=25). Enables gradient-based optimization.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Fatouros et al. 2022 eq.12';

MERGE (c:Concept {name: 'Tick Loss (VaR)'})
  SET c.definition   = 'L_tick = (alpha-hit_series)*(actual-forecast). Standard quantile regression loss. Asymmetric: larger penalty for under-prediction of losses at quantile alpha.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Fatouros et al. 2022 eq.13';

MERGE (c:Concept {name: 'Firm Loss (VaR)'})
  SET c.definition   = 'L_firm = hit*(1+(actual-VaR)^2) - c*(1-hit). Combines exceedance penalty with opportunity cost c of capital held against non-exceedances. c=1 by default.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Fatouros et al. 2022 eq.14';

MERGE (c:Concept {name: 'Unconditional Coverage Hypothesis'})
  SET c.definition   = 'H0: P(VaR exceedance) = 1-alpha. Tests whether model systematically over- or under-estimates risk. Violation rate should equal confidence level complement. Part of Christoffersen test.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Christoffersen 1998; WQU M3L1';

MERGE (c:Concept {name: 'Independence Hypothesis (VaR)'})
  SET c.definition   = 'H0: VaR exceedances are independently distributed (no clustering). Exceedance on day t should not predict exceedance on day t+1. Second component of Christoffersen LR test.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Christoffersen 1998; WQU M3L1';

MERGE (c:Concept {name: 'Christoffersen LR Test'})
  SET c.definition   = 'Likelihood ratio test combining unconditional coverage and independence hypotheses for VaR validity. Two sub-tests: LR_uc and LR_ind. Implemented in lr_bt function (Bayer).',
      c.category     = 'var_backtesting',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Christoffersen 1998; Bayer backtest.py';

MERGE (c:Concept {name: 'Dynamic Quantile Test'})
  SET c.definition   = 'Tests VaR exceedance independence via linear regression of hit series on lagged hits. H0: all regression coefficients = 0 (chi-square test). Engle & Managanelli. dq_bt in Bayer.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Engle & Managanelli; WQU M3L1';


// -----------------------------------------------------------------------------
// 57. CONCEPT NODES — TRANSFORMER ARCHITECTURE (M3L3)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Transformer Architecture'})
  SET c.definition   = 'Neural network replacing RNN recurrence with attention mechanism. Encoder-decoder structure. Multi-head self-attention + FFN sublayers per layer. State-of-the-art for sequence modeling (Vaswani et al. 2017).',
      c.category     = 'deep_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Vaswani et al. 2017; WQU M3L3';

MERGE (c:Concept {name: 'Attention Mechanism'})
  SET c.definition   = 'Maps query Q to weighted sum of values V using key K compatibility. Attention(Q,K,V)=softmax(QK^T/sqrt(d_k))V. Weights learned via training. Captures variable-range dependencies.',
      c.category     = 'deep_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Vaswani et al. 2017 "Attention is All You Need"';

MERGE (c:Concept {name: 'Multi-Head Self-Attention (MHSA)'})
  SET c.definition   = 'Multiple parallel attention heads on different subspaces. Each head learns different dependency patterns. Outputs concatenated and projected. Enables diverse temporal feature capture.',
      c.category     = 'deep_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Vaswani et al. 2017; WQU M3L3';

MERGE (c:Concept {name: 'Encoder-Decoder Model'})
  SET c.definition   = 'Encoder: neural network projecting inputs to latent feature vectors (feature extraction). Decoder: maps feature vectors to output predictions. Standard for seq2seq tasks. Transformer uses attention not RNN cells.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L3';

MERGE (c:Concept {name: 'Positional Encoding'})
  SET c.definition   = 'Adds sequence position information to input embeddings. Necessary because attention has no inherent order. PE(pos,2i)=sin(pos/10000^(2i/d)), PE(pos,2i+1)=cos(pos/10000^(2i/d)).',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Vaswani et al. 2017; WQU M3L3';

MERGE (c:Concept {name: 'Feed-Forward Network (FFN)'})
  SET c.definition   = 'Position-wise fully connected sublayer in transformer. Applied independently to each position after attention. Two linear transformations with ReLU: FFN(x)=max(0,xW1+b1)W2+b2.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Vaswani et al. 2017; WQU M3L3';

MERGE (c:Concept {name: 'Encoder-Only Transformer (Time Series)'})
  SET c.definition   = 'For time-series prediction, decoder omitted. Encoder output directly compared to next-step observations. Training by minimising prediction error. Simpler than full seq2seq transformer.',
      c.category     = 'deep_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L3; Ramos-Perez et al.';

MERGE (c:Concept {name: 'Multi-Transformer (Ramos-Perez)'})
  SET c.definition   = 'Transformer architecture adapted for S&P 500 volatility forecasting. Outperforms GARCH and LSTM especially on high-dimensional datasets. Multiple transformer layers for volatility sequence.',
      c.category     = 'deep_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'Ramos-Perez et al. Mathematics 2021';


// -----------------------------------------------------------------------------
// 58. CONCEPT → CATEGORY RELATIONSHIPS (v0.5.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept), (cat:Category)
WHERE c.category = cat.name
  AND c.menu_context IN ['MLModel', 'RiskMgr']
  AND c.source CONTAINS 'M3'
MERGE (c)-[:BELONGS_TO]->(cat);

// OS algorithm internals — scoped
MATCH (c:Concept {name:'Local Volatility (Rolling Window)'}),       (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Theoretical Volatility (Jump-Filtered)'}),  (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Local Vol with Order Statistics'}),          (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Jump Indicator Array'}),                     (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'kSmallestCDF'}),                             (cat:Category {name:'order_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Convergence Criterion (OS Algorithm)'}),     (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Return Renormalization'}),                   (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Rolling Correlation (125-day)'}),            (cat:Category {name:'risk_metrics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'VaR Backtesting'}),                          (cat:Category {name:'var_backtesting'}) MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// 59. NEW RELATIONSHIP TYPES: TRAINED_BY, EVALUATED_BY
// TRAINED_BY: connects ML model concept to its optimizer/training procedure
// EVALUATED_BY: connects forecasting concept to its backtesting/evaluation metric
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'DeepAR'}),  (b:Concept {name:'Adam Optimizer'})   MERGE (a)-[:TRAINED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'Adam Optimizer'})   MERGE (a)-[:TRAINED_BY]->(b);
MATCH (a:Concept {name:'Long Short-Term Memory (LSTM)'}),(b:Concept {name:'Adam Optimizer'}) MERGE (a)-[:TRAINED_BY]->(b);
MATCH (a:Concept {name:'Multi-Transformer (Ramos-Perez)'}),(b:Concept {name:'Adam Optimizer'}) MERGE (a)-[:TRAINED_BY]->(b);

MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'VaR Backtesting'})              MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'Christoffersen LR Test'})       MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'Dynamic Quantile Test'})        MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'Quadratic Loss (VaR)'})         MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'Tick Loss (VaR)'})              MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}), (b:Concept {name:'Smooth Loss (VaR)'})            MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'Multi-Transformer (Ramos-Perez)'}),(b:Concept {name:'VaR Backtesting'}) MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'OS Volatility Estimator'}),(b:Concept {name:'VaR Backtesting'}) MERGE (a)-[:EVALUATED_BY]->(b);


// -----------------------------------------------------------------------------
// 60. PREREQUISITE RELATIONSHIPS — ALL V0.5.0 BATCHES
// -----------------------------------------------------------------------------

// -- OS Algorithm internal chain --
MATCH (a:Concept {name:'OS Volatility Estimator'}),              (b:Concept {name:'Local Volatility (Rolling Window)'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Local Volatility (Rolling Window)'}),    (b:Concept {name:'Theoretical Volatility (Jump-Filtered)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Theoretical Volatility (Jump-Filtered)'}),(b:Concept {name:'Local Vol with Order Statistics'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Indicator Array'}),                  (b:Concept {name:'Local Vol with Order Statistics'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Indicator Array'}),                  (b:Concept {name:'Theoretical Volatility (Jump-Filtered)'})MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'kSmallestCDF'}),                          (b:Concept {name:'Local Vol with Order Statistics'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Incomplete Beta Function'}),              (b:Concept {name:'kSmallestCDF'})                          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Order Statistic CDF'}),                   (b:Concept {name:'kSmallestCDF'})                          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Return Renormalization'}),                (b:Concept {name:'kSmallestCDF'})                          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gaussian Reference Distribution'}),       (b:Concept {name:'kSmallestCDF'})                          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Convergence Criterion (OS Algorithm)'}),  (b:Concept {name:'Local Vol with Order Statistics'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Local Vol with Order Statistics'}),       (b:Concept {name:'OS Volatility Estimator'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Classification'}),                   (b:Concept {name:'Jump Indicator Array'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Threshold (Theta)'}),                (b:Concept {name:'Jump Indicator Array'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Local Vol with Order Statistics'}),       (b:Concept {name:'Integrated Variance'})                   MERGE (a)-[:PREREQ_OF]->(b);

// -- RNN hierarchy chain --
MATCH (a:Concept {name:'Recurrent Neural Network (RNN)'}),        (b:Concept {name:'Gated Recurrent Unit (GRU)'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gated Recurrent Unit (GRU)'}),            (b:Concept {name:'Long Short-Term Memory (LSTM)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Long Short-Term Memory (LSTM)'}),         (b:Concept {name:'DeepAR'})                                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DeepAR'}),                                (b:Concept {name:'DeepVaR'})                               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probabilistic Forecasting'}),             (b:Concept {name:'DeepAR'})                                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probabilistic Forecasting'}),             (b:Concept {name:'DeepVaR'})                               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Student-t Output Distribution'}),         (b:Concept {name:'DeepAR'})                                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GluonTS'}),                               (b:Concept {name:'DeepAR'})                                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GluonTS'}),                               (b:Concept {name:'DeepVaR'})                               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Adam Optimizer'}),                        (b:Concept {name:'DeepAR'})                                MERGE (a)-[:PREREQ_OF]->(b);

// -- DeepVaR → Portfolio VaR --
MATCH (a:Concept {name:'DeepVaR'}),                               (b:Concept {name:'Portfolio VaR (DeepVaR)'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Rolling Correlation (125-day)'}),         (b:Concept {name:'Portfolio VaR (DeepVaR)'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),                      (b:Concept {name:'Rolling Correlation (125-day)'})         MERGE (a)-[:PREREQ_OF]->(b);

// -- VaR Backtesting chain --
MATCH (a:Concept {name:'Hit Variable (VaR)'}),                    (b:Concept {name:'VaR Backtesting'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Hit Variable (VaR)'}),                    (b:Concept {name:'Quadratic Loss (VaR)'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Hit Variable (VaR)'}),                    (b:Concept {name:'Smooth Loss (VaR)'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Hit Variable (VaR)'}),                    (b:Concept {name:'Tick Loss (VaR)'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Hit Variable (VaR)'}),                    (b:Concept {name:'Firm Loss (VaR)'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Unconditional Coverage Hypothesis'}),     (b:Concept {name:'Christoffersen LR Test'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Independence Hypothesis (VaR)'}),         (b:Concept {name:'Christoffersen LR Test'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Christoffersen LR Test'}),                (b:Concept {name:'VaR Backtesting'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Dynamic Quantile Test'}),                 (b:Concept {name:'VaR Backtesting'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Quantile Regression'}),                   (b:Concept {name:'Dynamic Quantile Test'})                MERGE (a)-[:PREREQ_OF]->(b);

// -- Transformer chain --
MATCH (a:Concept {name:'Attention Mechanism'}),                   (b:Concept {name:'Multi-Head Self-Attention (MHSA)'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Multi-Head Self-Attention (MHSA)'}),      (b:Concept {name:'Transformer Architecture'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Feed-Forward Network (FFN)'}),            (b:Concept {name:'Transformer Architecture'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Positional Encoding'}),                   (b:Concept {name:'Transformer Architecture'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Encoder-Decoder Model'}),                 (b:Concept {name:'Transformer Architecture'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Recurrent Neural Network (RNN)'}),        (b:Concept {name:'Encoder-Decoder Model'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Encoder-Only Transformer (Time Series)'}),(b:Concept {name:'Multi-Transformer (Ramos-Perez)'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Encoder-Only Transformer (Time Series)'}),(b:Concept {name:'Multi-Transformer (Ramos-Perez)'})      MERGE (a)-[:PREREQ_OF]->(b);

// -- Cross-domain: deep learning → risk management --
MATCH (a:Concept {name:'DeepVaR'}),                               (b:Concept {name:'Systemic Risk Measurement'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Multi-Transformer (Ramos-Perez)'}),       (b:Concept {name:'Realized Variance'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Long Short-Term Memory (LSTM)'}),         (b:Concept {name:'Non-Stationarity'})                     MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probabilistic Forecasting'}),             (b:Concept {name:'Stress Testing'})                       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'OS Volatility Estimator'}),               (b:Concept {name:'Realized Variance'})                    MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// 61. GENERALIZES_TO — RNN HIERARCHY
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Recurrent Neural Network (RNN)'}), (b:Concept {name:'Gated Recurrent Unit (GRU)'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_reset_and_update_gates'}]->(b);
MATCH (a:Concept {name:'Gated Recurrent Unit (GRU)'}),     (b:Concept {name:'Long Short-Term Memory (LSTM)'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_input_forget_output_memory_gates'}]->(b);
MATCH (a:Concept {name:'Long Short-Term Memory (LSTM)'}),  (b:Concept {name:'DeepAR'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_probabilistic_output_distribution'}]->(b);
MATCH (a:Concept {name:'Encoder-Decoder Model'}),          (b:Concept {name:'Transformer Architecture'})
  MERGE (a)-[:GENERALIZES_TO {by:'replacing_recurrence_with_attention'}]->(b);


// -----------------------------------------------------------------------------
// 62. FORMULA NODES — DEEP LEARNING & BACKTESTING BATCH
// -----------------------------------------------------------------------------
UNWIND [
  {id: 'f_attention', name: 'Scaled Dot-Product Attention', expression: 'Attention(Q,K,V) = softmax(QKᵀ/sqrt(d_k))·V', latex: '\\text{Attention}(Q,K,V) = \\text{softmax}\\!\\left(\\frac{QK^\\top}{\\sqrt{d_k}}\\right)V', params: ['Q','K','V','d_k'], output: 'attention_weighted_values'},
  {id: 'f_deepar_loglik', name: 'DeepAR Log-Likelihood Objective', expression: 'L = Σᵢ Σₜ log l(z_{i,t} | θ(h_{i,t}))', latex: '\\mathcal{L} = \\sum_{i=1}^N\\sum_{t=t_0}^T \\log\\ell\\!\\left(z_{i,t}\\,\\big|\\,\\theta\\!\\left(\\mathbf{h}_{i,t}\\right)\\right)', params: ['z_it','θ','h_it','N','T'], output: 'log_likelihood'},
  {id: 'f_deepvar_portfolio', name: 'DeepVaR Portfolio VaR', expression: 'VaR_p = sqrt(V · R · Vᵀ)', latex: 'VaR_p = \\sqrt{\\mathbf{V} \\mathbf{R} \\mathbf{V}^\\top}', params: ['V','R'], output: 'portfolio_var'},
  {id: 'f_quadratic_loss', name: 'Quadratic VaR Loss', expression: 'L_quad = hit * (1 + (actual - forecast)²)', latex: 'L_{\\text{quad}} = I_t \\cdot \\left(1 + (r_t - \\widehat{VaR}_t)^2\\right)', params: ['I_t','r_t','VaR_hat'], output: 'quadratic_loss'},
  {id: 'f_smooth_loss', name: 'Smooth VaR Loss', expression: 'L_smooth = (alpha - (1+exp(delta*(actual-forecast)))⁻¹) * (actual-forecast)', latex: 'L_{\\text{smooth}} = \\left(\\alpha - \\frac{1}{1+e^{\\delta(r_t-\\widehat{VaR}_t)}}\\right)(r_t - \\widehat{VaR}_t)', params: ['alpha','delta','r_t','VaR_hat'], output: 'smooth_loss'},
  {id: 'f_tick_loss', name: 'Tick (Quantile) VaR Loss', expression: 'L_tick = (alpha - hit_series) * (actual - forecast)', latex: 'L_{\\text{tick}} = (\\alpha - I_t)(r_t - \\widehat{VaR}_t)', params: ['alpha','I_t','r_t','VaR_hat'], output: 'tick_loss'},
  {id: 'f_firm_loss', name: 'Firm VaR Loss', expression: 'L_firm = hit*(1+(actual-VaR)²) - c*(1-hit)', latex: 'L_{\\text{firm}} = I_t\\!\\left(1+(r_t-\\widehat{VaR}_t)^2\\right) - c(1-I_t)', params: ['I_t','r_t','VaR_hat','c'], output: 'firm_loss'},
  {id: 'f_positional_encoding', name: 'Transformer Positional Encoding', expression: 'PE(pos,2i)=sin(pos/10000^(2i/d)); PE(pos,2i+1)=cos(pos/10000^(2i/d))', latex: 'PE_{(pos,2i)}=\\sin\\!\\left(\\frac{pos}{10000^{2i/d}}\\right),\\quad PE_{(pos,2i+1)}=\\cos\\!\\left(\\frac{pos}{10000^{2i/d}}\\right)', params: ['pos','i','d'], output: 'position_embedding'},
  {id: 'f_hit_rate', name: 'VaR Hit Rate (Violation Rate)', expression: 'Hit Rate = mean(I_t) = (1/T)·Σ 1{actual_t < VaR_t}', latex: '\\bar{I} = \\frac{1}{T}\\sum_{t=1}^T \\mathbf{1}\\{r_t < \\widehat{VaR}_t\\}', params: ['r_t','VaR_hat','T'], output: 'violation_rate'}
] AS data
MERGE (f:Formula {id: data.id})
SET f.name = data.name,
    f.expression = data.expression,
    f.latex = data.latex,
    f.params = data.params,
    f.output = data.output
RETURN count(f) AS formulas_processed;
// -----------------------------------------------------------------------------
// 63. CONCEPT → FORMULA RELATIONSHIPS (v0.5.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Attention Mechanism'}),            (f:Formula {id:'f_attention'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Multi-Head Self-Attention (MHSA)'}),(f:Formula {id:'f_attention'})         MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'DeepAR'}),                         (f:Formula {id:'f_deepar_loglik'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'DeepVaR'}),                        (f:Formula {id:'f_deepvar_portfolio'})  MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Portfolio VaR (DeepVaR)'}),        (f:Formula {id:'f_deepvar_portfolio'})  MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Quadratic Loss (VaR)'}),           (f:Formula {id:'f_quadratic_loss'})     MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Smooth Loss (VaR)'}),              (f:Formula {id:'f_smooth_loss'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Tick Loss (VaR)'}),                (f:Formula {id:'f_tick_loss'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Firm Loss (VaR)'}),                (f:Formula {id:'f_firm_loss'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Hit Variable (VaR)'}),             (f:Formula {id:'f_hit_rate'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'VaR Backtesting'}),                (f:Formula {id:'f_hit_rate'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Positional Encoding'}),            (f:Formula {id:'f_positional_encoding'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Transformer Architecture'}),       (f:Formula {id:'f_attention'})          MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// 64. STRATEGY NODES — DEEP LEARNING VAR & TRANSFORMER VOL FORECAST
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'DeepVaR Risk Overlay'})
  SET s.derived_from         = 'DeepVaR',
      s.description          = 'Use DeepVaR probabilistic forecasts to set dynamic position-level VaR limits. Scale gross exposure when portfolio VaR_p exceeds risk budget. Rolling 125-day correlation for aggregation.',
      s.formula_ref          = 'f_deepvar_portfolio',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_var_confidence = 0.99,
      s.param_risk_budget    = 0.02,
      s.param_corr_window    = 125,
      s.risk_weight          = 0.90,
      s.strategy_type        = 'overlay',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Transformer Vol Forecast'})
  SET s.derived_from         = 'Multi-Transformer (Ramos-Perez)',
      s.description          = 'Use encoder-only transformer to forecast next-period realized volatility. Enter long/short variance swap based on transformer vol forecast vs current variance swap strike. Signal generated daily.',
      s.formula_ref          = 'f_attention',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_lookback       = 60,
      s.param_forecast_h     = 5,
      s.param_vol_diff_entry = 0.02,
      s.risk_weight          = 0.70,
      s.strategy_type        = 'alpha',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

// Strategy → Concept relationships
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (c:Concept {name:'DeepVaR'})                         MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (c:Concept {name:'Portfolio VaR (DeepVaR)'})         MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(c:Concept {name:'Multi-Transformer (Ramos-Perez)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(c:Concept {name:'Variance Swap'})                   MERGE (s)-[:DERIVED_FROM]->(c);

// Strategy → Formula relationships
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (f:Formula {id:'f_deepvar_portfolio'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (f:Formula {id:'f_kelly'})             MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(f:Formula {id:'f_attention'})         MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(f:Formula {id:'f_var_swap_payoff'})   MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(f:Formula {id:'f_kelly'})             MERGE (s)-[:HAS_FORMULA]->(f);

// Regime activations
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (r:Regime {name:'HighVolatility'})     MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (r:Regime {name:'Crisis'})             MERGE (s)-[:ACTIVATED_BY {weight:1.00}]->(r);
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}),    (r:Regime {name:'SystemicStress'})     MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(r:Regime {name:'HighVolatility'})     MERGE (s)-[:ACTIVATED_BY {weight:0.80}]->(r);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(r:Regime {name:'MeanReverting'})      MERGE (s)-[:ACTIVATED_BY {weight:0.65}]->(r);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}),(r:Regime {name:'LowVolatility'})      MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);

// Overlay contradiction with naive vol strategy
MATCH (a:Strategy {name:'DeepVaR Risk Overlay'}),    (b:Strategy {name:'Volatility Mean Reversion'})
  MERGE (a)-[:CONTRADICTED_BY]->(b);


// -----------------------------------------------------------------------------
// 65. NEW AGENT QUERY PATTERNS (v0.5.0)
// -----------------------------------------------------------------------------

// Q16: Full deep learning chain from RNN to DeepVaR to portfolio risk
// MATCH path = (rnn:Concept {name:'Recurrent Neural Network (RNN)'})-[:PREREQ_OF|GENERALIZES_TO*1..6]->(var:Concept {name:'Portfolio VaR (DeepVaR)'})
// RETURN [n IN nodes(path) | n.name] AS chain, length(path) AS depth
// ORDER BY depth ASC LIMIT 5

// Q17: VaR backtesting metric suite for a given strategy
// MATCH (s:Strategy)-[:EVALUATED_BY]->(metric:Concept)
// WHERE s.name = $strategy_name
// RETURN metric.name AS metric, metric.definition AS description

// Q18: Transformer architecture component map
// MATCH (comp:Concept)-[:PREREQ_OF]->(t:Concept {name:'Transformer Architecture'})
// RETURN comp.name AS component, comp.definition AS role

// Q19: All overlay strategies and their activation regimes
// MATCH (s:Strategy {strategy_type:'overlay'})-[a:ACTIVATED_BY]->(r:Regime)
// RETURN s.name, r.name, a.weight ORDER BY a.weight DESC

// Q20: OS algorithm convergence path — from raw returns to continuous vol
// MATCH path = (raw:Concept {name:'Local Volatility (Rolling Window)'})-[:PREREQ_OF*1..6]->(out:Concept {name:'Integrated Variance'})
// RETURN [n IN nodes(path) | n.name] AS algorithm_steps

// =============================================================================
// END v0.5.0
// -----------------------------------------------------------------------------
// KG STATS AFTER v0.5.0 LOAD:
//   Concept nodes      : 155  (119 + 36 new)
//   Category nodes     : 34   (31 + 3 new)
//   Formula nodes      : 62   (53 + 9 new)
//   Strategy nodes     : 16   (14 + 2 new)
//   Regime nodes       : 7    (unchanged)
//   Ticker nodes       : 10   (unchanged)
//   PREREQ_OF edges    : ~200 (~145 + ~55 new)
//   GENERALIZES_TO     : 13   (9 + 4 new — RNN hierarchy)
//   ACTIVATED_BY edges : 33   (27 + 6 new)
//   CONTRADICTED_BY    : 10   (9 + 1 new)
//   HAS_FORMULA edges  : ~87  (~74 + ~13 new)
//   TRANSMITS_TO       : 6    (unchanged)
//   MONITORS           : 10   (unchanged)
//   REPLICATES_WITH    : 5    (unchanged)
//   HEDGES             : 4    (unchanged)
//   TRAINED_BY         : 4    (new relationship type)
//   EVALUATED_BY       : 8    (new relationship type)
// Total relationship types: 15
//   PREREQ_OF, BELONGS_TO, HAS_FORMULA, DERIVED_FROM,
//   ACTIVATED_BY, CONTRADICTED_BY, TRANSMITS_TO, MONITORS,
//   REPLICATES_WITH, HEDGES, GENERALIZES_TO,
//   TRAINED_BY, EVALUATED_BY,
//   CORRELATED_WITH (runtime), HAS_SIGNAL (runtime)
// Concept domains covered (cumulative):
//   Options & Vol | Factor Investing | Estimation | Systemic Risk |
//   Network Theory | Shadow Banking | Fire Sale | Contingent Claims |
//   Granger Causality | Information Theory | Variance Swaps | OTC |
//   Replication Theory | Levy & Jump Models | Order Statistics |
//   OS Volatility Estimation | Spanning Mechanics | Implicit Vol |
//   RNN / GRU / LSTM | DeepAR / DeepVaR | Probabilistic Forecasting |
//   VaR Backtesting | Transformer Architecture | Attention Mechanism
// =============================================================================


// =============================================================================
// v0.5.1 AUGMENTATION
// Purpose: Fill gaps left by v0.5.0 — missing RNN training internals, full
//   transformer sublayer inventory, GARCH baseline, Bipower Variation, Kupiec
//   POF test, Christoffersen conditional coverage, elicitability, Cholesky /
//   Ledoit-Wolf for portfolio VaR aggregation, and probabilistic calibration.
// Sources (same as v0.5.0, deeper extraction):
//   - Barndorff-Nielsen & Shephard (2004) — Bipower Variation
//   - Christoffersen (1998) — full joint test derivation
//   - Kupiec (1995) — Proportion of Failures
//   - Basel Committee BCBS (1996, 2019) — traffic-light back-test
//   - Gneiting (2011) — elicitability of quantiles
//   - Vaswani et al. (2017) — Add & Norm, Layer Norm, Dropout in transformer
//   - Engle & Ng (1993); Bollerslev (1986) — GARCH baseline
//   - Ledoit & Wolf (2004) — shrinkage correlation
//   - WQU M3L2 — GluonTS implementation details
// New concepts  : 18
// New formulas  : 7
// New rel type  : MOTIVATES (directional: problem → solution concept)
// =============================================================================


// -----------------------------------------------------------------------------
// A. SCHEMA VERSION NOTE
// -----------------------------------------------------------------------------
// Schema version: 0.5.1
// Changelog:
//   0.5.1 — RNN training internals (BPTT, vanishing gradient), transformer
//            sublayers (LayerNorm, residual connection, dropout), GARCH(1,1)
//            baseline, Bipower Variation, Kupiec POF, conditional coverage
//            hypothesis, elicitability, Cholesky decomposition for portfolio
//            VaR, Ledoit-Wolf shrinkage, GluonTS implementation nodes,
//            calibration / PICP metric, Pinball Loss alias.


// -----------------------------------------------------------------------------
// B. CONCEPT NODES — RNN TRAINING INTERNALS
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Backpropagation Through Time (BPTT)'})
  SET c.definition   = 'Unrolled gradient computation for RNNs: gradients propagated backwards through each time step. Computational graph is the unrolled RNN. Exact gradient but exponential complexity; truncated BPTT used in practice.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Werbos 1990; WQU M3L1';

MERGE (c:Concept {name: 'Vanishing Gradient Problem'})
  SET c.definition   = 'Gradient ∂L/∂h_t = Π_{k=t}^{T} ∂h_{k+1}/∂h_k shrinks exponentially for long sequences. Sigmoid/tanh activations saturate. Root cause motivating LSTM/GRU gating mechanisms.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Hochreiter 1991; Bengio et al. 1994';

MERGE (c:Concept {name: 'Exploding Gradient Problem'})
  SET c.definition   = 'Gradient norm grows unboundedly during BPTT for unstable weight matrices. Mitigated by gradient clipping (norm threshold). Dual problem to vanishing gradients in deep/recurrent networks.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Pascanu et al. 2013';


// -----------------------------------------------------------------------------
// C. CONCEPT NODES — TRANSFORMER SUBLAYERS (MISSING FROM v0.5.0)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Layer Normalization'})
  SET c.definition   = 'Normalises activations across feature dimension within each token: LN(x) = γ·(x-μ)/σ + β. Applied after attention and FFN sublayers in transformer (Add & Norm step). Stabilises training.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Ba et al. 2016; Vaswani et al. 2017';

MERGE (c:Concept {name: 'Residual Connection (Add & Norm)'})
  SET c.definition   = 'Skip connection around each transformer sublayer: output = LN(x + Sublayer(x)). Prevents degradation in deep networks. Enables stable gradient flow. Identical structure for attention and FFN blocks.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'He et al. 2016; Vaswani et al. 2017';

MERGE (c:Concept {name: 'Dropout Regularization'})
  SET c.definition   = 'Randomly zeroes activations with probability p during training. Applied to attention weights and sublayer outputs in transformer. Reduces overfitting. rate=0.1 standard for transformer; higher for small financial datasets.',
      c.category     = 'deep_learning',
      c.difficulty   = 'basic',
      c.menu_context = 'MLModel',
      c.source       = 'Srivastava et al. 2014; WQU M3L3';


// -----------------------------------------------------------------------------
// D. CONCEPT NODES — GARCH BASELINE & BIPOWER VARIATION
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'GARCH(1,1)'})
  SET c.definition   = 'Generalized ARCH: σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}. α+β<1 for covariance stationarity. Industry benchmark for volatility forecasting. Outperformed by Multi-Transformer on large panels (Ramos-Perez et al.).',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'Bollerslev 1986; Ramos-Perez et al. 2021';

MERGE (c:Concept {name: 'Bipower Variation'})
  SET c.definition   = 'BV = (π/2)·Σ|r_{t-1}|·|r_t|. Consistent estimator of integrated variance in presence of finite-activity jumps. Basis for separating continuous from jump quadratic variation: IV ≈ BV, JV = RV - BV.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Barndorff-Nielsen & Shephard 2004';

MERGE (c:Concept {name: 'Jump Quadratic Variation'})
  SET c.definition   = 'JV = RV - BV. Excess of realized variance over bipower variation attributable to price jumps. Under H0 (no jumps): JV/RV → 0. Used in jump tests to detect significant daily jumps.',
      c.category     = 'jump_models',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Barndorff-Nielsen & Shephard 2004';


// -----------------------------------------------------------------------------
// E. CONCEPT NODES — VAR BACKTESTING COMPLETENESS (MISSING FROM v0.5.0)
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Kupiec POF Test'})
  SET c.definition   = 'Proportion of Failures likelihood ratio test: LR_POF = -2·ln[(1-p)^(T-N)·p^N] + 2·ln[(1-N/T)^(T-N)·(N/T)^N]. p=confidence level, N=violations, T=observations. χ²(1) under H0.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Kupiec 1995';

MERGE (c:Concept {name: 'Conditional Coverage Hypothesis'})
  SET c.definition   = 'Joint test combining unconditional coverage and independence: LR_cc = LR_uc + LR_ind ~ χ²(2). Full Christoffersen (1998) test. Model passes only if exceedances are correct frequency AND unclustered.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Christoffersen 1998';

MERGE (c:Concept {name: 'Basel Traffic Light Test'})
  SET c.definition   = 'BCBS regulatory VaR backtest over 250 trading days at 99%. Green: ≤4 exceptions (accept). Yellow: 5–9 (supervisory discretion, capital add-on). Red: ≥10 (model rejected). Maps exception count to capital multiplier.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'BCBS 1996; Basel III FRTB 2019';

MERGE (c:Concept {name: 'Elicitability'})
  SET c.definition   = 'A risk measure is elicitable if it is the unique minimiser of some scoring function. Quantiles (VaR) are elicitable via tick/pinball loss. Expected Shortfall is NOT directly elicitable (Gneiting 2011). Justifies quantile regression for VaR.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Gneiting 2011; Fissler & Ziegel 2016';

MERGE (c:Concept {name: 'Pinball Loss'})
  SET c.definition   = 'Alternative name for tick (quantile) loss: ρ_α(u) = u·(α - 1{u<0}). Equivalent to L_tick = (α - I_t)·(actual - forecast). Scoring function whose expected value is minimised by the true α-quantile.',
      c.category     = 'var_backtesting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Koenker & Bassett 1978';


// -----------------------------------------------------------------------------
// F. CONCEPT NODES — PORTFOLIO VAR AGGREGATION INTERNALS
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Cholesky Decomposition'})
  SET c.definition   = 'Factorises positive-definite correlation matrix R = L·Lᵀ. Used to generate correlated scenarios and to compute portfolio VaR as VaR_p = sqrt(V·R·Vᵀ) efficiently. O(n³) but n=10 tickers is trivial.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M3L2; standard linear algebra';

MERGE (c:Concept {name: 'Ledoit-Wolf Shrinkage'})
  SET c.definition   = 'Regularised correlation/covariance estimator: Σ_LW = (1-α)·S + α·F. S=sample covariance, F=shrinkage target (e.g. identity scaled). Reduces estimation error for small T/large N. Oracle-optimal α via analytical formula.',
      c.category     = 'risk_metrics',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Ledoit & Wolf 2004';


// -----------------------------------------------------------------------------
// G. CONCEPT NODES — GLUTS IMPLEMENTATION & CALIBRATION
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'DeepAREstimator (GluonTS)'})
  SET c.definition   = 'GluonTS class instantiating DeepAR. Key constructor params: freq (data frequency), prediction_length, context_length (encoder lookback), num_layers, num_cells, cell_type (LSTM/GRU), dropout_rate, use_feat_dynamic_real.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L2; GluonTS docs';

MERGE (c:Concept {name: 'Prediction Interval Coverage Probability (PICP)'})
  SET c.definition   = 'PICP = (1/T)·Σ 1{y_t ∈ [ŷ_low,t, ŷ_high,t]}. Empirical coverage of predicted intervals. For a calibrated 95% interval: PICP ≈ 0.95. Key calibration metric alongside MPIW (mean predicted interval width).',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Khosravi et al. 2011; WQU M3L1';

MERGE (c:Concept {name: 'Calibration (Probabilistic Forecast)'})
  SET c.definition   = 'Forecaster is calibrated if stated probability α matches empirical frequency. For VaR: 95% VaR should be exceeded 5% of the time. Measured by PICP and probability integral transform (PIT) histogram uniformity.',
      c.category     = 'probabilistic_forecasting',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'Gneiting et al. 2007; WQU M3L1';


// -----------------------------------------------------------------------------
// H. CATEGORY MEMBERSHIP — v0.5.1 NODES
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Backpropagation Through Time (BPTT)'}),       (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Vanishing Gradient Problem'}),                  (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Exploding Gradient Problem'}),                  (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Layer Normalization'}),                         (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Residual Connection (Add & Norm)'}),            (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Dropout Regularization'}),                      (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'DeepAREstimator (GluonTS)'}),                   (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Prediction Interval Coverage Probability (PICP)'}),(cat:Category {name:'probabilistic_forecasting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Calibration (Probabilistic Forecast)'}),        (cat:Category {name:'probabilistic_forecasting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Kupiec POF Test'}),                             (cat:Category {name:'var_backtesting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Conditional Coverage Hypothesis'}),             (cat:Category {name:'var_backtesting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Basel Traffic Light Test'}),                    (cat:Category {name:'var_backtesting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Elicitability'}),                               (cat:Category {name:'var_backtesting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Pinball Loss'}),                                (cat:Category {name:'var_backtesting'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Cholesky Decomposition'}),                      (cat:Category {name:'risk_metrics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Ledoit-Wolf Shrinkage'}),                       (cat:Category {name:'risk_metrics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Bipower Variation'}),                           (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Jump Quadratic Variation'}),                    (cat:Category {name:'jump_models'}) MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// I. NEW RELATIONSHIP TYPE: MOTIVATES
// Directional: problem or limitation → solution or approach
// Semantics: node A exposes a shortcoming that node B addresses
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Vanishing Gradient Problem'}),       (b:Concept {name:'Long Short-Term Memory (LSTM)'})  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Vanishing Gradient Problem'}),       (b:Concept {name:'Gated Recurrent Unit (GRU)'})     MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Exploding Gradient Problem'}),       (b:Concept {name:'Gated Recurrent Unit (GRU)'})     MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),                 (b:Concept {name:'Ledoit-Wolf Shrinkage'})          MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),                 (b:Concept {name:'Rolling Correlation (125-day)'})  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Elicitability'}),                    (b:Concept {name:'Tick Loss (VaR)'})                MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Elicitability'}),                    (b:Concept {name:'Pinball Loss'})                   MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Vanishing Gradient Problem'}),       (b:Concept {name:'Attention Mechanism'})            MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Jump Quadratic Variation'}),         (b:Concept {name:'Local Vol with Order Statistics'}) MERGE (a)-[:MOTIVATES]->(b);


// -----------------------------------------------------------------------------
// J. PREREQUISITE CHAINS — v0.5.1
// -----------------------------------------------------------------------------

// RNN training internals chain
MATCH (a:Concept {name:'Backpropagation Through Time (BPTT)'}), (b:Concept {name:'Recurrent Neural Network (RNN)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Vanishing Gradient Problem'}),           (b:Concept {name:'Backpropagation Through Time (BPTT)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Exploding Gradient Problem'}),           (b:Concept {name:'Backpropagation Through Time (BPTT)'}) MERGE (a)-[:PREREQ_OF]->(b);

// Transformer sublayer completeness
MATCH (a:Concept {name:'Layer Normalization'}),                  (b:Concept {name:'Transformer Architecture'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Residual Connection (Add & Norm)'}),     (b:Concept {name:'Transformer Architecture'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Dropout Regularization'}),               (b:Concept {name:'Transformer Architecture'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Layer Normalization'}),                  (b:Concept {name:'Multi-Transformer (Ramos-Perez)'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Residual Connection (Add & Norm)'}),     (b:Concept {name:'Multi-Transformer (Ramos-Perez)'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Dropout Regularization'}),               (b:Concept {name:'DeepAR'})                            MERGE (a)-[:PREREQ_OF]->(b);

// GARCH baseline → comparison with Transformer
MATCH (a:Concept {name:'Heteroskedasticity (Time-Varying Vol)'}),(b:Concept {name:'GARCH(1,1)'})                        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GARCH(1,1)'}),                           (b:Concept {name:'Multi-Transformer (Ramos-Perez)'})  MERGE (a)-[:PREREQ_OF]->(b);

// Bipower Variation chain
MATCH (a:Concept {name:'Realized Variance'}),                    (b:Concept {name:'Bipower Variation'})                 MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bipower Variation'}),                    (b:Concept {name:'Jump Quadratic Variation'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Jump Quadratic Variation'}),             (b:Concept {name:'OS Volatility Estimator'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bipower Variation'}),                    (b:Concept {name:'Jump Classification'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bipower Variation'}),                    (b:Concept {name:'Integrated Variance'})               MERGE (a)-[:PREREQ_OF]->(b);

// VaR backtesting completeness chain
MATCH (a:Concept {name:'Kupiec POF Test'}),                      (b:Concept {name:'Christoffersen LR Test'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Kupiec POF Test'}),                      (b:Concept {name:'Unconditional Coverage Hypothesis'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Unconditional Coverage Hypothesis'}),    (b:Concept {name:'Conditional Coverage Hypothesis'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Independence Hypothesis (VaR)'}),        (b:Concept {name:'Conditional Coverage Hypothesis'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Coverage Hypothesis'}),      (b:Concept {name:'VaR Backtesting'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Kupiec POF Test'}),                      (b:Concept {name:'Basel Traffic Light Test'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Basel Traffic Light Test'}),             (b:Concept {name:'VaR Backtesting'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Pinball Loss'}),                         (b:Concept {name:'Dynamic Quantile Test'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Elicitability'}),                        (b:Concept {name:'VaR Backtesting'})                   MERGE (a)-[:PREREQ_OF]->(b);

// Calibration chain
MATCH (a:Concept {name:'Prediction Interval Coverage Probability (PICP)'}),(b:Concept {name:'Calibration (Probabilistic Forecast)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Calibration (Probabilistic Forecast)'}), (b:Concept {name:'Probabilistic Forecasting'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Calibration (Probabilistic Forecast)'}), (b:Concept {name:'DeepAR'})                           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Calibration (Probabilistic Forecast)'}), (b:Concept {name:'DeepVaR'})                          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Student-t Output Distribution'}),        (b:Concept {name:'Calibration (Probabilistic Forecast)'}) MERGE (a)-[:PREREQ_OF]->(b);

// Portfolio VaR aggregation internals
MATCH (a:Concept {name:'Cholesky Decomposition'}),               (b:Concept {name:'Portfolio VaR (DeepVaR)'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Ledoit-Wolf Shrinkage'}),                (b:Concept {name:'Rolling Correlation (125-day)'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Ledoit-Wolf Shrinkage'}),                (b:Concept {name:'Portfolio VaR (DeepVaR)'})            MERGE (a)-[:PREREQ_OF]->(b);

// Implementation node
MATCH (a:Concept {name:'GluonTS'}),                              (b:Concept {name:'DeepAREstimator (GluonTS)'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DeepAREstimator (GluonTS)'}),            (b:Concept {name:'DeepAR'})                             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Long Short-Term Memory (LSTM)'}),        (b:Concept {name:'DeepAREstimator (GluonTS)'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gated Recurrent Unit (GRU)'}),           (b:Concept {name:'DeepAREstimator (GluonTS)'})          MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// K. CONTRADICTED_BY — GARCH BASELINE VS DEEP LEARNING
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'GARCH(1,1)'}), (b:Concept {name:'Multi-Transformer (Ramos-Perez)'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Transformer outperforms GARCH on high-dim vol panels (Ramos-Perez et al. 2021)'}]->(b);

MATCH (a:Concept {name:'GARCH(1,1)'}), (b:Concept {name:'Long Short-Term Memory (LSTM)'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'LSTM captures nonlinear vol dynamics missed by linear GARCH recursion'}]->(b);

MATCH (a:Concept {name:'Elicitability'}), (b:Concept {name:'Expected Shortfall'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'ES is NOT elicitable (Gneiting 2011): no single scoring function uniquely identifies ES, complicating direct loss-based optimization'}]->(b);

MATCH (a:Concept {name:'Pinball Loss'}), (b:Concept {name:'Smooth Loss (VaR)'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Pinball loss is non-differentiable at zero; smooth loss trades exact quantile targeting for gradient-based optimizability'}]->(b);


// -----------------------------------------------------------------------------
// L. FORMULA NODES — v0.5.1
// -----------------------------------------------------------------------------
UNWIND [
  {id: 'f_garch11', name: 'GARCH(1,1) Variance Recursion', expression: 'σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}', latex: '\\sigma^2_t = \\omega + \\alpha\\,\\varepsilon^2_{t-1} + \\beta\\,\\sigma^2_{t-1}', params: ['ω','α','β','ε_t'], constraints: 'ω>0; α,β≥0; α+β<1 (stationarity)', output: 'conditional_variance'},
  {id: 'f_bipower_variation', name: 'Bipower Variation', expression: 'BV = (π/2) · Σ_{t=2}^{T} |r_{t-1}| · |r_t|', latex: 'BV = \\frac{\\pi}{2}\\sum_{t=2}^{T}|r_{t-1}|\\cdot|r_t|', params: ['r_t','T'], output: 'integrated_variance_estimate'},
  {id: 'f_jump_qv', name: 'Jump Quadratic Variation', expression: 'JV = RV - BV', latex: 'JV = RV - BV \\geq 0', params: ['RV','BV'], output: 'jump_variance'},
  {id: 'f_kupiec_pof', name: 'Kupiec POF Likelihood Ratio', expression: 'LR_POF = -2·ln[(1-p)^(T-N)·p^N] + 2·ln[(1-N/T)^(T-N)·(N/T)^N]', latex: 'LR_{POF} = -2\\ln\\!\\left[(1-p)^{T-N}p^N\\right] + 2\\ln\\!\\left[\\left(1-\\tfrac{N}{T}\\right)^{T-N}\\!\\!\\left(\\tfrac{N}{T}\\right)^N\\right]', params: ['p','N','T'], output: 'chi2_1_statistic'},
  {id: 'f_layer_norm', name: 'Layer Normalization', expression: 'LN(x) = γ · (x - μ) / σ + β', latex: 'LN(\\mathbf{x}) = \\gamma \\cdot \\frac{\\mathbf{x} - \\mu}{\\sigma} + \\beta', params: ['x','γ','β','μ','σ'], output: 'normalised_activation'},
  {id: 'f_picp', name: 'Prediction Interval Coverage Probability', expression: 'PICP = (1/T) · Σ 1{y_t ∈ [ŷ_low,t, ŷ_high,t]}', latex: 'PICP = \\frac{1}{T}\\sum_{t=1}^{T}\\mathbf{1}\\!\\left\\{y_t \\in [\\hat{y}^{low}_t,\\,\\hat{y}^{high}_t]\\right\\}', params: ['y_t','ŷ_low','ŷ_high','T'], output: 'empirical_coverage'},
  {id: 'f_ledoit_wolf', name: 'Ledoit-Wolf Shrinkage Estimator', expression: 'Σ_LW = (1 - α) · S + α · μ_S · I', latex: '\\hat{\\Sigma}_{LW} = (1-\\alpha)\\,S + \\alpha\\,\\mu_S\\,I', params: ['S','α','μ_S'], note: 'α solved analytically; μ_S = trace(S)/n scales identity target', output: 'shrinkage_covariance'}
] AS data
MERGE (f:Formula {id: data.id})
SET f.name = data.name,
    f.expression = data.expression,
    f.latex = data.latex,
    f.params = data.params,
    f.output = data.output,
    f.constraints = data.constraints,
    f.note = data.note
RETURN count(f) AS formulas_processed;
// -----------------------------------------------------------------------------
// M. CONCEPT → FORMULA RELATIONSHIPS (v0.5.1)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'GARCH(1,1)'}),                                   (f:Formula {id:'f_garch11'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Bipower Variation'}),                             (f:Formula {id:'f_bipower_variation'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Jump Quadratic Variation'}),                      (f:Formula {id:'f_jump_qv'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Kupiec POF Test'}),                               (f:Formula {id:'f_kupiec_pof'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Conditional Coverage Hypothesis'}),               (f:Formula {id:'f_kupiec_pof'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Layer Normalization'}),                           (f:Formula {id:'f_layer_norm'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Residual Connection (Add & Norm)'}),              (f:Formula {id:'f_layer_norm'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Prediction Interval Coverage Probability (PICP)'}),(f:Formula {id:'f_picp'})            MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Calibration (Probabilistic Forecast)'}),          (f:Formula {id:'f_picp'})             MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Ledoit-Wolf Shrinkage'}),                         (f:Formula {id:'f_ledoit_wolf'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Pinball Loss'}),                                  (f:Formula {id:'f_tick_loss'})        MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// N. EVALUATED_BY — extend to new backtesting nodes
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'DeepVaR'}),                    (b:Concept {name:'Kupiec POF Test'})               MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}),                    (b:Concept {name:'Conditional Coverage Hypothesis'}) MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepVaR'}),                    (b:Concept {name:'Basel Traffic Light Test'})       MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'GARCH(1,1)'}),                 (b:Concept {name:'Kupiec POF Test'})               MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'GARCH(1,1)'}),                 (b:Concept {name:'Basel Traffic Light Test'})      MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'Multi-Transformer (Ramos-Perez)'}),(b:Concept {name:'Prediction Interval Coverage Probability (PICP)'}) MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepAR'}),                     (b:Concept {name:'Calibration (Probabilistic Forecast)'}) MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'DeepAR'}),                     (b:Concept {name:'Prediction Interval Coverage Probability (PICP)'}) MERGE (a)-[:EVALUATED_BY]->(b);


// -----------------------------------------------------------------------------
// O. STRATEGY ENRICHMENT — add backtesting gate to DeepVaR Risk Overlay
// -----------------------------------------------------------------------------

MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}), (c:Concept {name:'Conditional Coverage Hypothesis'})
  MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}), (c:Concept {name:'Basel Traffic Light Test'})
  MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'DeepVaR Risk Overlay'}), (c:Concept {name:'Ledoit-Wolf Shrinkage'})
  MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}), (c:Concept {name:'GARCH(1,1)'})
  MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Transformer Vol Forecast'}), (f:Formula {id:'f_garch11'})
  MERGE (s)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// P. NEW AGENT QUERY PATTERNS (v0.5.1)
// -----------------------------------------------------------------------------

// Q21: Full RNN motivation chain — from vanishing gradient to LSTM to DeepVaR
// MATCH path = (p:Concept {name:'Vanishing Gradient Problem'})-[:MOTIVATES|PREREQ_OF*1..5]->(d:Concept {name:'DeepVaR'})
// RETURN [n IN nodes(path) | n.name] AS motivation_chain, length(path) AS depth ORDER BY depth ASC LIMIT 3

// Q22: VaR model validation suite — all evaluation methods for a strategy
// MATCH (s:Strategy)-[:EVALUATED_BY]->(m:Concept)
// WHERE s.name = $strategy_name
// RETURN m.name AS metric, m.difficulty AS complexity, m.source AS reference ORDER BY m.difficulty

// Q23: Transformer component inventory — all PREREQ_OF edges into Transformer Architecture
// MATCH (comp:Concept)-[:PREREQ_OF]->(t:Concept {name:'Transformer Architecture'})
// RETURN comp.name AS component, comp.definition AS role, comp.difficulty AS complexity

// Q24: GARCH vs Deep Learning comparison — all CONTRADICTED_BY from GARCH
// MATCH (g:Concept {name:'GARCH(1,1)'})-[r:CONTRADICTED_BY]->(dl:Concept)
// RETURN dl.name AS superior_model, r.reason AS evidence

// Q25: Portfolio VaR construction path — from individual forecasts to aggregated risk
// MATCH path = (d:Concept {name:'DeepAR'})-[:PREREQ_OF*1..4]->(p:Concept {name:'Portfolio VaR (DeepVaR)'})
// RETURN [n IN nodes(path) | n.name] AS construction_steps

// Q26: Bipower Variation → OS estimator full dependency graph
// MATCH path = (b:Concept {name:'Bipower Variation'})-[:PREREQ_OF|MOTIVATES*1..4]->(os:Concept)
// WHERE os.category = 'jump_models'
// RETURN [n IN nodes(path) | n.name] AS jump_vol_chain


// =============================================================================
// END v0.5.1
// -----------------------------------------------------------------------------
// INCREMENTAL KG STATS (v0.5.1 additions only):
//   Concept nodes added    : 18
//   Formula nodes added    : 7
//   PREREQ_OF edges added  : ~40
//   MOTIVATED_BY edges     : 9    (new relationship type MOTIVATES)
//   EVALUATED_BY edges     : 8    (extensions)
//   CONTRADICTED_BY        : 4
//   HAS_FORMULA            : 11
//   BELONGS_TO             : 18
//   TRAINED_BY             : 0    (no new training relationships)
// Total relationship types : 16   (added MOTIVATES)
//
// CUMULATIVE KG STATS AFTER v0.5.1:
//   Concept nodes      : 173  (155 + 18)
//   Category nodes     : 34   (unchanged)
//   Formula nodes      : 69   (62 + 7)
//   Strategy nodes     : 16   (unchanged)
//   Regime nodes       : 7    (unchanged)
//   Ticker nodes       : 10   (unchanged)
//   PREREQ_OF edges    : ~240 (~200 + ~40)
//   GENERALIZES_TO     : 13   (unchanged)
//   MOTIVATES          : 9    (new)
//   ACTIVATED_BY       : 33   (unchanged)
//   CONTRADICTED_BY    : 14   (10 + 4)
//   HAS_FORMULA        : ~98  (~87 + 11)
//   BELONGS_TO         : ~120 (extended)
//   TRANSMITS_TO       : 6    (unchanged)
//   MONITORS           : 10   (unchanged)
//   REPLICATES_WITH    : 5    (unchanged)
//   HEDGES             : 4    (unchanged)
//   TRAINED_BY         : 4    (unchanged)
//   EVALUATED_BY       : 16   (8 + 8)
//   CORRELATED_WITH    : (runtime)
//   HAS_SIGNAL         : (runtime)
// Total relationship types: 16
//   PREREQ_OF, BELONGS_TO, HAS_FORMULA, DERIVED_FROM,
//   ACTIVATED_BY, CONTRADICTED_BY, TRANSMITS_TO, MONITORS,
//   REPLICATES_WITH, HEDGES, GENERALIZES_TO,
//   TRAINED_BY, EVALUATED_BY, MOTIVATES,
//   CORRELATED_WITH (runtime), HAS_SIGNAL (runtime)
// New concept domains added in v0.5.1:
//   RNN Training Internals (BPTT, Vanishing/Exploding Gradient) |
//   Transformer Sublayers (LayerNorm, Residual, Dropout) |
//   GARCH(1,1) Baseline | Bipower Variation | Jump QV |
//   Kupiec POF | Conditional Coverage | Basel Traffic Light |
//   Elicitability | Pinball Loss | Cholesky Decomposition |
//   Ledoit-Wolf Shrinkage | DeepAREstimator | PICP | Calibration
// =============================================================================


// =============================================================================
// v0.6.0 — EXTREME VALUE THEORY & ASYMMETRIC GARCH FAMILY
// Sources:
//   - "Risk Modeling with Extreme Value Theory" (WQU M4L1, Singh et al.)
//   - "Block Maxima: Indonesian Gold" (WQU M4L2, Pratiwi et al.)
//   - "The Theorem and Politics of Extreme Values" (WQU M4L3, Nortey et al.)
//   - "Extreme Innovations in Value at Risk Modeling" (WQU M4L4, Omari et al.)
//   - "Multi-Transformer in Action" (WQU M3L4, Ramos-Perez et al.)
// New domains: EVT (POT & BMM), GEV family, GARCH extensions (EGARCH/GJR/APARCH),
//   leverage asymmetry, political risk, bagging ensemble
// -----------------------------------------------------------------------------
// New concepts  : 28
// New categories: 2  (extreme_value_theory, political_risk)
// New formulas  : 10
// New strategies: 2  (GARCH-EVT VaR Overlay, Asymmetric Vol Regime Signal)
// New rel type  : FITTED_TO (model → distributional target)
// =============================================================================


// -----------------------------------------------------------------------------
// A. SCHEMA VERSION NOTE
// -----------------------------------------------------------------------------
// Schema version: 0.6.0
// Changelog:
//   0.6.0 — Extreme Value Theory: POT, BMM, GPD, GEV family (Gumbel/Frechet/
//            Weibull), Fisher-Tippett Theorem, MDA, GARCH-EVT combination,
//            GPD parameter estimators (MLE, Hill, Moment), threshold selection,
//            mean excess function. Asymmetric GARCH: EGARCH, GJR-GARCH, APARCH
//            (unifying generalization), leverage effect, innovation term,
//            GJR unconditional variance, mean-reversion condition.
//            Political Risk five components. Bagging for Multi-Transformer.
//            Multi-Head Attention formula completeness.


// -----------------------------------------------------------------------------
// B. NEW CATEGORY NODES
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'extreme_value_theory', display: 'Extreme Value Theory'});
MERGE (:Category {name: 'political_risk',        display: 'Political Risk'});


// -----------------------------------------------------------------------------
// C. CONCEPT NODES — EXTREME VALUE THEORY FRAMEWORK
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Extreme Value Theory (EVT)'})
  SET c.definition   = 'Statistical framework for modelling rare, extreme observations in the tails of distributions. Two main approaches: Peaks Over Threshold (POT) and Block Maxima Method (BMM). Underpins tail-risk VaR and ES estimation beyond historical simulation.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al.';

MERGE (c:Concept {name: 'Peaks Over Threshold (POT)'})
  SET c.definition   = 'EVT approach selecting all observations above a threshold u. Exceedances follow the Generalized Pareto Distribution (GPD) in the limit. More data-efficient than BMM; preferred when serial independence holds. POT threshold need not equal VaR threshold.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al. 1480';

MERGE (c:Concept {name: 'Block Maxima Method (BMM)'})
  SET c.definition   = 'EVT approach dividing observation period into non-overlapping equal-length blocks and taking the single maximum per block. Block maxima fitted to GEV distribution. Preferred over POT when short-range dependence exists within blocks (iid not required between blocks).',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; WQU M4L2; Ferreira & de Haan 2014';

MERGE (c:Concept {name: 'Generalized Pareto Distribution (GPD)'})
  SET c.definition   = 'Two-parameter distribution for POT exceedances: ξ (shape/tail index) and σ (scale). CDF: F(y)=1-(1+ξy/σ)^(-1/ξ). ξ=0: exponential decay (thin tail); ξ>0: power-law heavy tail (financial returns); ξ<0: bounded upper tail. MLE used to fit.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al. 1480-1481';

MERGE (c:Concept {name: 'Generalized Extreme Value (GEV) Distribution'})
  SET c.definition   = 'Family of distributions for BMM block maxima, unifying Gumbel (ξ=0), Frechet (ξ>0), and Weibull (ξ<0) distributions. Parameters: μ (location/mode), σ (scale, must be >0), ξ (shape). CDF: exp(-(1+ξ(x-μ)/σ)^(-1/ξ)).',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; WQU M4L2; Singh et al. 1479';

MERGE (c:Concept {name: 'Gumbel Distribution'})
  SET c.definition   = 'GEV subfamily with ξ=0. Location parameter μ is the mode (not mean — mean > mode due to positive skew). Thin-tailed: Normal distribution in MDA of Gumbel. Block maxima of Normal samples follow Gumbel asymptotically.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L2; Pratiwi et al. 3';

MERGE (c:Concept {name: 'Frechet Distribution'})
  SET c.definition   = 'GEV subfamily with ξ>0. Power-law heavy tail. Financial return distributions (fat-tailed) are in the MDA of Frechet. Appropriate for equity/commodity extreme loss modelling. Tail heaviness increases with ξ.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al. 1479';

MERGE (c:Concept {name: 'Weibull Distribution (EVT)'})
  SET c.definition   = 'GEV subfamily with ξ<0. Bounded upper tail: distribution has finite upper endpoint. Used for naturally bounded quantities (e.g. wind speed, flood heights). Not appropriate for financial returns which exhibit heavy upper tails.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al. 1479';

MERGE (c:Concept {name: 'GEV Shape Parameter (ξ)'})
  SET c.definition   = 'ξ determines GEV subfamily: ξ=0 → Gumbel; ξ>0 → Frechet (heavy tail); ξ<0 → Weibull (bounded). In the Gumbel standardization, ξ does not appear. Estimated via MLE. For equity returns, ξ typically in (0, 0.5).',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L2; Pratiwi et al. 3';

MERGE (c:Concept {name: 'Threshold Selection (POT)'})
  SET c.definition   = 'Choice of u in POT: too low → GPD approximation poor; too high → too few exceedances, high variance. Methods: mean excess function plot (linearity indicates GPD fit), stability of GPD parameter estimates, 90th-95th percentile as practical starting points.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al. 1481';

MERGE (c:Concept {name: 'Mean Excess Function'})
  SET c.definition   = 'e(u) = E[X-u | X>u]. Expected exceedance above threshold u. Linear in u for GPD: e(u) = (σ+ξu)/(1-ξ). Used to select POT threshold: plot e(u) vs u; linearity above u_0 indicates GPD fit from u_0. Also called mean residual life.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al.';

MERGE (c:Concept {name: 'Block Size Selection (BMM)'})
  SET c.definition   = 'Tradeoff in BMM: small blocks → poor GEV convergence (bias); large blocks → fewer maxima observations (variance). Common choices: monthly blocks (21 trading days) for financial data, annual blocks (252 days). Governs number of observations N/block_size.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L2; Ferreira & de Haan 2014';

MERGE (c:Concept {name: 'GPD MLE Estimator'})
  SET c.definition   = 'Maximum likelihood estimation of GPD parameters (ξ, σ) from POT exceedances. Standard approach (Singh et al. 1481). scipy.stats.genpareto.fit() in Python. Asymptotically efficient. Requires sufficient exceedances (N_u > 50 rule of thumb).',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al. 1481';

MERGE (c:Concept {name: 'Hill Estimator'})
  SET c.definition   = 'Non-parametric tail index estimator: ξ_Hill = (1/k)·Σ_{i=1}^{k} ln(X_{(n-i+1)}/X_{(n-k)}). Consistent for ξ>0 (Frechet domain). k=number of order statistics used. Bias-variance tradeoff in k selection. Alternative to MLE for heavy tails.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Hill 1975';

MERGE (c:Concept {name: 'Moment Estimator (EVT)'})
  SET c.definition   = 'Method-of-moments estimator for GPD parameters. Equates sample moments (mean, variance of exceedances) to theoretical GPD moments. Simple but less efficient than MLE. Alternative for small samples where MLE may not converge.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1';

MERGE (c:Concept {name: 'GARCH-EVT Model'})
  SET c.definition   = 'Combination of GARCH volatility model with EVT tail fitting. Procedure: (1) fit GARCH to returns, extract standardised residuals; (2) apply POT/BMM to residuals; (3) reconstruct VaR/ES by multiplying GPD/GEV quantile by conditional volatility. Captures both volatility clustering and fat tails.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L1; Singh et al.; Omari et al. 2017';

MERGE (c:Concept {name: 'Fisher-Tippett Theorem'})
  SET c.definition   = 'The "CLT of EVT": if X₁,X₂,... IID and (M_n-d_n)/c_n →_L G for suitable sequences c_n>0, d_n, then G must be a GEV distribution. Equivalently: POT exceedances converge to GPD as threshold increases. Distribution must be in MDA of GEV.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L3; Haugh Columbia; Herman CSU';

MERGE (c:Concept {name: 'Maximum Domain of Attraction (MDA)'})
  SET c.definition   = 'X ∈ MDA(G) if ∃ sequences c_n>0, d_n: (M_n-d_n)/c_n →_L G as n→∞. MDA(Gumbel): Normal, Exponential, Gamma. MDA(Frechet): Student-t, Pareto, stable distributions. MDA(Weibull): Uniform, Beta. Financial returns → MDA(Frechet).',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L3; Cizek et al.; Haugh Columbia p.7';

MERGE (c:Concept {name: 'GEV-GPD Relationship'})
  SET c.definition   = 'GEV distribution is a special case of GPD under certain parameterizations (Ding 2008). The two are "exchangeable" when GPD threshold is sufficiently high. POT (GPD) and BMM (GEV) approaches are linked through this relationship rather than being independent alternatives.',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L3; Ding et al. 2008 pp.509-510';

MERGE (c:Concept {name: 'GEVMLE (Block Maxima Estimator)'})
  SET c.definition   = 'Maximum likelihood estimator for GEV parameters (ξ, μ, σ) from block maxima. Implemented as GEVMLE class in Steven\'s Python EVT package. Returns point estimates with 95% confidence intervals: tail (ξ), loc (μ), scale (σ).',
      c.category     = 'extreme_value_theory',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L2; Pratiwi et al.; Steven GitHub evt';


// -----------------------------------------------------------------------------
// D. CONCEPT NODES — ASYMMETRIC GARCH FAMILY
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'EGARCH'})
  SET c.definition   = 'Exponential GARCH (Nelson 1991): models log variance, not variance. No non-negativity parameter restrictions needed. Captures leverage asymmetry via γ parameter (typically γ<0): ln(σ²_t) = ω + β·ln(σ²_{t-1}) + γ·z_{t-1} + α·[|z_{t-1}|-E|z|]. Both sides exponentiated.',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Nelson 1991; WQU M4L4; Omari et al. 852';

MERGE (c:Concept {name: 'GJR-GARCH'})
  SET c.definition   = 'Glosten-Jagannathan-Runkle GARCH: adds indicator I_{t-1}=1{ε_{t-1}<μ} to GARCH. σ²_t = ω + (α+γI_{t-1})ε²_{t-1} + βσ²_{t-1}. γ>0 captures "bad news" effect. Mean-reversion: α+γ/2+β<1. Unconditional variance: ω/(1-α-β-γ/2).',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Glosten-Jagannathan-Runkle 1993; WQU M4L4';

MERGE (c:Concept {name: 'APARCH'})
  SET c.definition   = 'Asymmetric Power ARCH: σ^δ_t = ω + Σαᵢ(|ε_{t-i}|-γᵢε_{t-i})^δ + Σβⱼσ^δ_{t-j}. Unifies: δ=2,γ=0,β=0→ARCH; δ=2,γ=0→GARCH; δ=2→GJR-GARCH; δ=0→EGARCH. Power δ estimated freely (US stocks: ~1.43-1.524). Most flexible ARCH-family model.',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'Ding et al. 1993; WQU M4L4; McKenzie & Mitchell';

MERGE (c:Concept {name: 'Leverage Effect (Volatility)'})
  SET c.definition   = 'Empirical asymmetry: negative return shocks increase future volatility more than positive shocks of equal magnitude. Observed as negative correlation between returns and VIX (S&P 500 1990-2017). Motivated originally by leverage ratio mechanics; now understood as broader phenomenon (Engle).',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M4L4; Sun & Wu 2018; Engle VLab';

MERGE (c:Concept {name: 'Innovation Term (GARCH)'})
  SET c.definition   = 'Return shock ε_t = r_t - μ in GARCH framework. Also called "innovation." Standardised innovation z_t = ε_t/σ_t. Sign of ε_{t-1} drives asymmetric response in EGARCH (via γ·z_{t-1}) and GJR-GARCH (via indicator variable I_{t-1}).',
      c.category     = 'volatility',
      c.difficulty   = 'basic',
      c.menu_context = 'Model',
      c.source       = 'WQU M4L4; Omari et al. 851';

MERGE (c:Concept {name: 'GJR-GARCH Mean Reversion Condition'})
  SET c.definition   = 'Volatility is mean-reverting in GJR-GARCH iff α + γ/2 + β < 1. The ½ multiplier follows from symmetry assumption: E[I_{t-1}] = 0.5 under Normality. Analogous to α+β<1 in standard GARCH for stationarity.',
      c.category     = 'volatility',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M4L4; V-Lab NYU';

MERGE (c:Concept {name: 'APARCH Power Parameter (δ)'})
  SET c.definition   = 'Free positive real parameter in APARCH. Governs functional form: δ=2 reduces to variance (GARCH/GJR family); δ=0 gives log variance (EGARCH family). Estimated from data. Empirical values for US stocks: 1.43 (McKenzie & Mitchell), 1.524. Improves goodness-of-fit over fixed-power models.',
      c.category     = 'volatility',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M4L4; McKenzie & Mitchell; Schmidt 2021';


// -----------------------------------------------------------------------------
// E. CONCEPT NODES — POLITICAL RISK
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Political Risk'})
  SET c.definition   = 'Geopolitical risk arising from changes in ruling party, fiscal/monetary policy shifts, regulatory agendas, elections, civil conflict, and external wars. Significant driver of stock market volatility regimes. Five components (Sun & Liu 2018): government stability, socioeconomic conditions, investment profile, internal conflict, external conflict.',
      c.category     = 'political_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M4L3; Nortey et al.; Sun & Liu 2018';

MERGE (c:Concept {name: 'Political Dummy Variable (GARCH)'})
  SET c.definition   = 'Binary indicator variable embedded in GARCH/EGARCH/GJR-GARCH to capture political events: election vs. non-election years, stable vs. unstable governments. Agarwal & Agarwal find significant effects on Indian stock market; Wang & Lin use for Taiwan democratization effect.',
      c.category     = 'political_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M4L3; Agarwal & Agarwal 2018; Wang & Lin';

MERGE (c:Concept {name: 'Uncertainty Premium'})
  SET c.definition   = 'Markets abhor uncertainty; expected positive return once political uncertainty resolves in either direction. Wang & Lin (Taiwan): positive returns after electoral outcome clarified regardless of winner. Mechanism: risk premium compressed as uncertainty removed.',
      c.category     = 'political_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M4L3; Wang & Lin 237';


// -----------------------------------------------------------------------------
// F. CONCEPT NODES — MULTI-TRANSFORMER BAGGING COMPLETENESS
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Bagging (Bootstrap Aggregating)'})
  SET c.definition   = 'Ensemble method: each model trained on random subsample (typically 90% in Multi-Transformer). Predictions averaged across 5 transformers. Reduces overfitting and output variance compared to single model. Ramos-Perez et al. use 5 transformers × 90% subsample.',
      c.category     = 'deep_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L4; Ramos-Perez et al. pp.12-14';

MERGE (c:Concept {name: 'Multi-Head Attention Formula'})
  SET c.definition   = 'MultiHead(Q,K,V) = Concat(head₁,...,headₕ)·W^O where headᵢ = Attention(Q·Wᵢ^Q, K·Wᵢ^K, V·Wᵢ^V). Projection matrices: Wᵢ^Q ∈ R^(d_model×d_k), Wᵢ^K ∈ R^(d_model×d_k), Wᵢ^V ∈ R^(d_model×d_v), W^O ∈ R^(hd_v×d_model). Batched: (batch_size, seq_len, embed_dim).',
      c.category     = 'deep_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M3L4; Vaswani et al. 2017; Ramos-Perez GitHub';


// -----------------------------------------------------------------------------
// G. CATEGORY MEMBERSHIP — v0.6.0 NODES
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Extreme Value Theory (EVT)'}),           (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Peaks Over Threshold (POT)'}),           (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Block Maxima Method (BMM)'}),            (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Generalized Pareto Distribution (GPD)'}),(cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Generalized Extreme Value (GEV) Distribution'}),(cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Gumbel Distribution'}),                  (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Frechet Distribution'}),                 (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Weibull Distribution (EVT)'}),           (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GEV Shape Parameter (ξ)'}),              (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Threshold Selection (POT)'}),            (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Mean Excess Function'}),                 (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Block Size Selection (BMM)'}),           (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GPD MLE Estimator'}),                    (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Hill Estimator'}),                       (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Moment Estimator (EVT)'}),               (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GARCH-EVT Model'}),                      (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Fisher-Tippett Theorem'}),               (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Maximum Domain of Attraction (MDA)'}),   (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GEV-GPD Relationship'}),                 (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GEVMLE (Block Maxima Estimator)'}),      (cat:Category {name:'extreme_value_theory'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'EGARCH'}),                               (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GJR-GARCH'}),                            (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'APARCH'}),                               (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Leverage Effect (Volatility)'}),         (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Innovation Term (GARCH)'}),              (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GJR-GARCH Mean Reversion Condition'}),   (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'APARCH Power Parameter (δ)'}),           (cat:Category {name:'volatility'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Political Risk'}),                       (cat:Category {name:'political_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Political Dummy Variable (GARCH)'}),     (cat:Category {name:'political_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Uncertainty Premium'}),                  (cat:Category {name:'political_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Bagging (Bootstrap Aggregating)'}),      (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Multi-Head Attention Formula'}),         (cat:Category {name:'deep_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// H. NEW RELATIONSHIP TYPE: FITTED_TO
// Semantics: model/estimator is applied to (fitted to) a target distribution
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Peaks Over Threshold (POT)'}),           (b:Concept {name:'Generalized Pareto Distribution (GPD)'})         MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'Block Maxima Method (BMM)'}),            (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'})   MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'GPD MLE Estimator'}),                    (b:Concept {name:'Generalized Pareto Distribution (GPD)'})         MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'Hill Estimator'}),                       (b:Concept {name:'Generalized Pareto Distribution (GPD)'})         MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'Moment Estimator (EVT)'}),               (b:Concept {name:'Generalized Pareto Distribution (GPD)'})         MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'GEVMLE (Block Maxima Estimator)'}),      (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'})  MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'GARCH-EVT Model'}),                      (b:Concept {name:'Generalized Pareto Distribution (GPD)'})         MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'Gumbel Distribution'}),                  (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'})  MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'Frechet Distribution'}),                 (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'})  MERGE (a)-[:FITTED_TO]->(b);
MATCH (a:Concept {name:'Weibull Distribution (EVT)'}),           (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'})  MERGE (a)-[:FITTED_TO]->(b);


// -----------------------------------------------------------------------------
// I. GENERALIZES_TO — APARCH SUBSUMES GARCH FAMILY
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'APARCH'}), (b:Concept {name:'GARCH(1,1)'})
  MERGE (a)-[:GENERALIZES_TO {by:'setting_delta=2_gamma=0'}]->(b);
MATCH (a:Concept {name:'APARCH'}), (b:Concept {name:'GJR-GARCH'})
  MERGE (a)-[:GENERALIZES_TO {by:'setting_delta=2'}]->(b);
MATCH (a:Concept {name:'APARCH'}), (b:Concept {name:'EGARCH'})
  MERGE (a)-[:GENERALIZES_TO {by:'setting_delta=0'}]->(b);
MATCH (a:Concept {name:'Generalized Extreme Value (GEV) Distribution'}), (b:Concept {name:'Gumbel Distribution'})
  MERGE (a)-[:GENERALIZES_TO {by:'setting_xi=0'}]->(b);
MATCH (a:Concept {name:'Generalized Extreme Value (GEV) Distribution'}), (b:Concept {name:'Frechet Distribution'})
  MERGE (a)-[:GENERALIZES_TO {by:'setting_xi_gt_0'}]->(b);
MATCH (a:Concept {name:'Generalized Extreme Value (GEV) Distribution'}), (b:Concept {name:'Weibull Distribution (EVT)'})
  MERGE (a)-[:GENERALIZES_TO {by:'setting_xi_lt_0'}]->(b);


// -----------------------------------------------------------------------------
// J. MOTIVATES — ASYMMETRIC GARCH
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Leverage Effect (Volatility)'}), (b:Concept {name:'EGARCH'})      MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Leverage Effect (Volatility)'}), (b:Concept {name:'GJR-GARCH'})   MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Leverage Effect (Volatility)'}), (b:Concept {name:'APARCH'})      MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Fat Tails'}),                    (b:Concept {name:'Extreme Value Theory (EVT)'}) MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Fat Tails'}),                    (b:Concept {name:'Frechet Distribution'})       MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Political Risk'}),               (b:Concept {name:'Political Dummy Variable (GARCH)'}) MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Bagging (Bootstrap Aggregating)'}),(b:Concept {name:'Multi-Transformer (Ramos-Perez)'}) MERGE (a)-[:MOTIVATES]->(b);


// -----------------------------------------------------------------------------
// K. PREREQUISITE CHAINS — v0.6.0
// -----------------------------------------------------------------------------

// EVT framework hierarchy
MATCH (a:Concept {name:'Extreme Value Theory (EVT)'}),       (b:Concept {name:'Peaks Over Threshold (POT)'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Extreme Value Theory (EVT)'}),       (b:Concept {name:'Block Maxima Method (BMM)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fisher-Tippett Theorem'}),           (b:Concept {name:'Extreme Value Theory (EVT)'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Maximum Domain of Attraction (MDA)'}),(b:Concept {name:'Fisher-Tippett Theorem'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fisher-Tippett Theorem'}),           (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Fisher-Tippett Theorem'}),           (b:Concept {name:'Generalized Pareto Distribution (GPD)'}) MERGE (a)-[:PREREQ_OF]->(b);

// POT chain
MATCH (a:Concept {name:'Threshold Selection (POT)'}),        (b:Concept {name:'Peaks Over Threshold (POT)'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Mean Excess Function'}),             (b:Concept {name:'Threshold Selection (POT)'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Generalized Pareto Distribution (GPD)'}),(b:Concept {name:'Peaks Over Threshold (POT)'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GPD MLE Estimator'}),                (b:Concept {name:'Peaks Over Threshold (POT)'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Hill Estimator'}),                   (b:Concept {name:'Peaks Over Threshold (POT)'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Moment Estimator (EVT)'}),           (b:Concept {name:'Peaks Over Threshold (POT)'})        MERGE (a)-[:PREREQ_OF]->(b);

// BMM chain
MATCH (a:Concept {name:'Block Size Selection (BMM)'}),       (b:Concept {name:'Block Maxima Method (BMM)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Generalized Extreme Value (GEV) Distribution'}),(b:Concept {name:'Block Maxima Method (BMM)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GEVMLE (Block Maxima Estimator)'}),  (b:Concept {name:'Block Maxima Method (BMM)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GEV Shape Parameter (ξ)'}),          (b:Concept {name:'Generalized Extreme Value (GEV) Distribution'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gumbel Distribution'}),              (b:Concept {name:'Block Maxima Method (BMM)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Frechet Distribution'}),             (b:Concept {name:'Block Maxima Method (BMM)'})         MERGE (a)-[:PREREQ_OF]->(b);

// GARCH-EVT combination
MATCH (a:Concept {name:'GARCH(1,1)'}),                       (b:Concept {name:'GARCH-EVT Model'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'EGARCH'}),                           (b:Concept {name:'GARCH-EVT Model'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GJR-GARCH'}),                        (b:Concept {name:'GARCH-EVT Model'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Peaks Over Threshold (POT)'}),       (b:Concept {name:'GARCH-EVT Model'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GARCH-EVT Model'}),                  (b:Concept {name:'VaR Backtesting'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GARCH-EVT Model'}),                  (b:Concept {name:'Expected Shortfall'})                MERGE (a)-[:PREREQ_OF]->(b);

// Asymmetric GARCH chain
MATCH (a:Concept {name:'GARCH(1,1)'}),                       (b:Concept {name:'EGARCH'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GARCH(1,1)'}),                       (b:Concept {name:'GJR-GARCH'})                         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'EGARCH'}),                           (b:Concept {name:'APARCH'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GJR-GARCH'}),                        (b:Concept {name:'APARCH'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Innovation Term (GARCH)'}),          (b:Concept {name:'EGARCH'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Innovation Term (GARCH)'}),          (b:Concept {name:'GJR-GARCH'})                         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GJR-GARCH Mean Reversion Condition'}),(b:Concept {name:'GJR-GARCH'})                        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'APARCH Power Parameter (δ)'}),       (b:Concept {name:'APARCH'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Heteroskedasticity (Time-Varying Vol)'}),(b:Concept {name:'EGARCH'})                        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Heteroskedasticity (Time-Varying Vol)'}),(b:Concept {name:'GJR-GARCH'})                     MERGE (a)-[:PREREQ_OF]->(b);

// GEV-GPD relationship
MATCH (a:Concept {name:'GEV-GPD Relationship'}),             (b:Concept {name:'Peaks Over Threshold (POT)'})        MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GEV-GPD Relationship'}),             (b:Concept {name:'Block Maxima Method (BMM)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Generalized Pareto Distribution (GPD)'}),(b:Concept {name:'GEV-GPD Relationship'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Generalized Extreme Value (GEV) Distribution'}),(b:Concept {name:'GEV-GPD Relationship'})   MERGE (a)-[:PREREQ_OF]->(b);

// Political risk chain
MATCH (a:Concept {name:'Political Risk'}),                   (b:Concept {name:'Uncertainty Premium'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Political Dummy Variable (GARCH)'}), (b:Concept {name:'EGARCH'})                            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Political Dummy Variable (GARCH)'}), (b:Concept {name:'GJR-GARCH'})                         MERGE (a)-[:PREREQ_OF]->(b);

// Multi-head attention completeness
MATCH (a:Concept {name:'Attention Mechanism'}),              (b:Concept {name:'Multi-Head Attention Formula'})       MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Multi-Head Attention Formula'}),     (b:Concept {name:'Multi-Head Self-Attention (MHSA)'})   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bagging (Bootstrap Aggregating)'}),  (b:Concept {name:'Multi-Transformer (Ramos-Perez)'})   MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain: EVT → VaR backtesting
MATCH (a:Concept {name:'Peaks Over Threshold (POT)'}),       (b:Concept {name:'VaR Backtesting'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Frechet Distribution'}),             (b:Concept {name:'Systemic Risk Measurement'})          MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Maximum Domain of Attraction (MDA)'}),(b:Concept {name:'Non-Stationarity'})                 MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// L. EVALUATED_BY — ASYMMETRIC GARCH MODELS
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'EGARCH'}),   (b:Concept {name:'VaR Backtesting'})          MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'GJR-GARCH'}),(b:Concept {name:'VaR Backtesting'})          MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'APARCH'}),   (b:Concept {name:'VaR Backtesting'})          MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'GARCH-EVT Model'}),(b:Concept {name:'Kupiec POF Test'})    MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'GARCH-EVT Model'}),(b:Concept {name:'Christoffersen LR Test'}) MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'EGARCH'}),   (b:Concept {name:'Christoffersen LR Test'})   MERGE (a)-[:EVALUATED_BY]->(b);
MATCH (a:Concept {name:'GJR-GARCH'}),(b:Concept {name:'Christoffersen LR Test'})   MERGE (a)-[:EVALUATED_BY]->(b);


// -----------------------------------------------------------------------------
// M. CONTRADICTED_BY — EVT vs GARCH / NORMAL TAIL ASSUMPTION
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Generalized Pareto Distribution (GPD)'}), (b:Concept {name:'Student-t Output Distribution'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Student-t parameterised from data; GPD fitted non-parametrically to observed tail exceedances — GPD does not assume parametric return distribution'}]->(b);

MATCH (a:Concept {name:'EGARCH'}), (b:Concept {name:'GARCH(1,1)'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'GARCH(1,1) treats positive and negative shocks symmetrically; EGARCH explicitly models the leverage asymmetry γ<0 that GARCH(1,1) misses'}]->(b);

MATCH (a:Concept {name:'GJR-GARCH'}), (b:Concept {name:'GARCH(1,1)'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'GARCH(1,1) cannot capture the bad-news amplification effect; GJR-GARCH adds indicator variable to address this asymmetry'}]->(b);

MATCH (a:Concept {name:'Frechet Distribution'}), (b:Concept {name:'Gumbel Distribution'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Financial returns have power-law heavy tails (Frechet MDA); Gumbel (thin-tail, e.g. Normal) materially underestimates extreme loss probability'}]->(b);


// -----------------------------------------------------------------------------
// N. FORMULA NODES — v0.6.0
// -----------------------------------------------------------------------------

UNWIND [
  {id: 'f_egarch', name: 'EGARCH Log-Variance Equation', expression: 'ln(σ²_t) = ω + β·ln(σ²_{t-1}) + γ·z_{t-1} + α·(|z_{t-1}| - E|z|)', latex: '\\ln\\sigma^2_t = \\omega + \\beta\\ln\\sigma^2_{t-1} + \\gamma z_{t-1} + \\alpha\\!\\left(|z_{t-1}| - \\mathbb{E}|z|\\right)', params: ['ω','β','γ','α','z_t'], note: 'z_t = ε_t/σ_t standardised innovation; γ<0 captures leverage effect; no non-negativity restrictions', output: 'log_conditional_variance'},
  {id: 'f_gjr_garch', name: 'GJR-GARCH Variance Equation', expression: 'σ²_t = ω + (α + γ·I_{t-1})·ε²_{t-1} + β·σ²_{t-1}', latex: '\\sigma^2_t = \\omega + (\\alpha + \\gamma I_{t-1})\\varepsilon^2_{t-1} + \\beta\\sigma^2_{t-1}', params: ['ω','α','γ','β','I_t'], note: 'I_{t-1}=1{ε_{t-1}<μ}; mean reversion: α+γ/2+β<1', output: 'conditional_variance'},
  {id: 'f_gjr_unconditional', name: 'GJR-GARCH Unconditional Variance', expression: 'σ² = ω / (1 - α - β - γ/2)', latex: '\\sigma^2 = \\frac{\\omega}{1 - \\alpha - \\beta - \\gamma/2}', params: ['ω','α','β','γ'], note: 'Exists iff α+γ/2+β<1; ½ from symmetry of innovation distribution', output: 'unconditional_variance'},
  {id: 'f_aparch', name: 'APARCH Power Variance Equation', expression: 'σ^δ_t = ω + Σᵢ αᵢ·(|ε_{t-i}| - γᵢ·ε_{t-i})^δ + Σⱼ βⱼ·σ^δ_{t-j}', latex: '\\sigma^\\delta_t = \\omega + \\sum_i \\alpha_i(|\\varepsilon_{t-i}| - \\gamma_i\\varepsilon_{t-i})^\\delta + \\sum_j \\beta_j\\sigma^\\delta_{t-j}', params: ['ω','αᵢ','γᵢ','βⱼ','δ'], note: 'δ>0 free parameter; δ=2,γ=0→GARCH; δ=2→GJR; δ=0→EGARCH; empirical δ≈1.43-1.52 for US equities', output: 'power_conditional_variance'},
  {id: 'f_gpd_var', name: 'GPD-Based VaR Formula', expression: 'VaR_p = u + (σ/ξ)·[(n/N_u·(1-p))^(-ξ) - 1]', latex: 'VaR_p = u + \\frac{\\sigma}{\\xi}\\!\\left[\\left(\\frac{n}{N_u(1-p)}\\right)^{-\\xi} - 1\\right]', params: ['u','σ','ξ','n','N_u','p'], note: 'u=threshold; N_u=exceedances above u; n=total obs; p=confidence level', output: 'var_quantile'},
  {id: 'f_gpd_es', name: 'GPD-Based Expected Shortfall', expression: 'ES_p = (VaR_p + σ - ξ·u) / (1 - ξ)', latex: 'ES_p = \\frac{VaR_p + \\sigma - \\xi u}{1 - \\xi}', params: ['VaR_p','σ','ξ','u'], note: 'Valid for ξ<1; closed-form ES from GPD fit', output: 'expected_shortfall'},
  {id: 'f_gev_cdf', name: 'GEV Cumulative Distribution Function', expression: 'F(x) = exp(-(1 + ξ·(x-μ)/σ)^(-1/ξ))', latex: 'F(x) = \\exp\\!\\left(-\\left(1 + \\xi\\,\\frac{x-\\mu}{\\sigma}\\right)^{-1/\\xi}\\right)', params: ['x','ξ','μ','σ'], note: 'ξ→0 limit gives Gumbel: exp(-exp(-(x-μ)/σ))', output: 'gev_cdf'},
  {id: 'f_mean_excess', name: 'Mean Excess Function (GPD Linearity)', expression: 'e(u) = (σ + ξ·u) / (1 - ξ)', latex: 'e(u) = \\frac{\\sigma + \\xi u}{1 - \\xi}', params: ['σ','ξ','u'], note: 'Linear in u ⟺ exceedances follow GPD. Plot e(u) vs u; choose threshold u₀ where linearity begins', output: 'expected_exceedance'},
  {id: 'f_mha', name: 'Multi-Head Attention', expression: 'MultiHead(Q,K,V) = Concat(head₁,...,headₕ)·W^O  where headᵢ = Attention(Q·Wᵢ^Q, K·Wᵢ^K, V·Wᵢ^V)', latex: '\\text{MultiHead}(Q,K,V) = \\text{Concat}(\\text{head}_1,\\ldots,\\text{head}_h)W^O', params: ['Q','K','V','h','W^Q_i','W^K_i','W^V_i','W^O'], note: 'Batched implementation: each tensor is (batch_size, seq_len, embed_dim); h=5 in Multi-Transformer', output: 'multi_head_attention'},
  {id: 'f_hill', name: 'Hill Tail Index Estimator', expression: 'ξ_Hill = (1/k) · Σᵢ₌₁ᵏ ln(X_{(n-i+1)} / X_{(n-k)})', latex: '\\hat{\\xi}_{Hill} = \\frac{1}{k}\\sum_{i=1}^{k}\\ln\\frac{X_{(n-i+1)}}{X_{(n-k)}}', params: ['X','k','n'], note: 'Valid for ξ>0 (Frechet MDA only); k choice is bias-variance tradeoff', output: 'tail_index'}
] AS data
MERGE (f:Formula {id: data.id})
SET f.name = data.name,
    f.expression = data.expression,
    f.latex = data.latex,
    f.params = data.params,
    f.output = data.output,
    f.note = data.note
RETURN count(f) AS formulas_processed;
// -----------------------------------------------------------------------------
// O. CONCEPT → FORMULA RELATIONSHIPS (v0.6.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'EGARCH'}),                               (f:Formula {id:'f_egarch'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'GJR-GARCH'}),                            (f:Formula {id:'f_gjr_garch'})        MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'GJR-GARCH Mean Reversion Condition'}),   (f:Formula {id:'f_gjr_unconditional'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'GJR-GARCH'}),                            (f:Formula {id:'f_gjr_unconditional'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'APARCH'}),                               (f:Formula {id:'f_aparch'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'APARCH Power Parameter (δ)'}),           (f:Formula {id:'f_aparch'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Generalized Pareto Distribution (GPD)'}),(f:Formula {id:'f_gpd_var'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Peaks Over Threshold (POT)'}),           (f:Formula {id:'f_gpd_var'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Expected Shortfall'}),                   (f:Formula {id:'f_gpd_es'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'GARCH-EVT Model'}),                      (f:Formula {id:'f_gpd_var'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'GARCH-EVT Model'}),                      (f:Formula {id:'f_gpd_es'})           MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Generalized Extreme Value (GEV) Distribution'}),(f:Formula {id:'f_gev_cdf'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Block Maxima Method (BMM)'}),            (f:Formula {id:'f_gev_cdf'})          MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Mean Excess Function'}),                 (f:Formula {id:'f_mean_excess'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Threshold Selection (POT)'}),            (f:Formula {id:'f_mean_excess'})      MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Multi-Head Attention Formula'}),         (f:Formula {id:'f_mha'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Multi-Head Self-Attention (MHSA)'}),     (f:Formula {id:'f_mha'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Hill Estimator'}),                       (f:Formula {id:'f_hill'})             MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// P. STRATEGY NODES — v0.6.0
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'GARCH-EVT VaR Overlay'})
  SET s.derived_from         = 'GARCH-EVT Model',
      s.description          = 'Dynamic VaR estimation pipeline: (1) fit GJR-GARCH or EGARCH to returns capturing leverage asymmetry, (2) extract standardised residuals, (3) apply POT with GPD MLE to residuals, (4) reconstruct VaR = σ_t × GPD_quantile. Backtested via Christoffersen CC test. Position sizing scaled inversely to VaR_t/VaR_budget.',
      s.formula_ref          = 'f_gpd_var',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_var_confidence = 0.99,
      s.param_pot_threshold  = 0.90,
      s.param_garch_model    = 'GJR-GARCH',
      s.risk_weight          = 0.85,
      s.strategy_type        = 'overlay',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

MERGE (s:Strategy {name: 'Asymmetric Vol Regime Signal'})
  SET s.derived_from         = 'EGARCH',
      s.description          = 'Exploit leverage asymmetry: after large negative return shock, EGARCH forecasts vol spike disproportionate to positive shock of same size. Enter short vol position (short variance swap or short straddle) when EGARCH vol forecast normalises post-spike. Signal: EGARCH_vol_t / EGARCH_vol_{t-5} < 0.85.',
      s.formula_ref          = 'f_egarch',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_lookback       = 5,
      s.param_normalise_ratio = 0.85,
      s.param_entry_lag      = 1,
      s.risk_weight          = 0.60,
      s.strategy_type        = 'alpha',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

// Strategy → Concept
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (c:Concept {name:'GARCH-EVT Model'})              MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (c:Concept {name:'GJR-GARCH'})                    MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (c:Concept {name:'Generalized Pareto Distribution (GPD)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(c:Concept {name:'EGARCH'})                       MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(c:Concept {name:'Leverage Effect (Volatility)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(c:Concept {name:'Variance Swap'})                MERGE (s)-[:DERIVED_FROM]->(c);

// Strategy → Formula
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (f:Formula {id:'f_gpd_var'})    MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (f:Formula {id:'f_gpd_es'})     MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (f:Formula {id:'f_gjr_garch'})  MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (f:Formula {id:'f_kelly'})      MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(f:Formula {id:'f_egarch'})     MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(f:Formula {id:'f_var_swap_payoff'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(f:Formula {id:'f_kelly'})      MERGE (s)-[:HAS_FORMULA]->(f);

// Regime activations
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (r:Regime {name:'HighVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.95}]->(r);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (r:Regime {name:'Crisis'})           MERGE (s)-[:ACTIVATED_BY {weight:1.00}]->(r);
MATCH (s:Strategy {name:'GARCH-EVT VaR Overlay'}),      (r:Regime {name:'SystemicStress'})   MERGE (s)-[:ACTIVATED_BY {weight:0.90}]->(r);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(r:Regime {name:'HighVolatility'})  MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);
MATCH (s:Strategy {name:'Asymmetric Vol Regime Signal'}),(r:Regime {name:'MeanReverting'})   MERGE (s)-[:ACTIVATED_BY {weight:0.70}]->(r);

// Contradictions
MATCH (a:Strategy {name:'GARCH-EVT VaR Overlay'}),(b:Strategy {name:'DeepVaR Risk Overlay'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Both are VaR overlay strategies; running both simultaneously double-counts risk and over-constrains position limits'}]->(b);
MATCH (a:Strategy {name:'Asymmetric Vol Regime Signal'}),(b:Strategy {name:'Volatility Mean Reversion'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Both trade mean-reversion of vol; entry/exit signals conflict on timing — Asymmetric Vol uses EGARCH forecast, Vol MR uses realized vol ratio'}]->(b);


// -----------------------------------------------------------------------------
// Q. NEW AGENT QUERY PATTERNS (v0.6.0)
// -----------------------------------------------------------------------------

// Q27: EVT model selection — POT vs BMM with regime context
// MATCH (evt:Concept {name:'Extreme Value Theory (EVT)'})-[:PREREQ_OF]->(method:Concept)
// MATCH (method)-[:FITTED_TO]->(dist:Concept)
// RETURN method.name AS approach, dist.name AS target_distribution, method.definition AS when_to_use

// Q28: Full GARCH-EVT pipeline from raw returns to VaR
// MATCH path = (g:Concept)-[:PREREQ_OF*1..5]->(e:Strategy {name:'GARCH-EVT VaR Overlay'})
// WHERE g.category = 'volatility'
// RETURN [n IN nodes(path) | n.name] AS pipeline ORDER BY length(path) ASC LIMIT 5

// Q29: APARCH generalization tree — all models subsumed by APARCH
// MATCH (a:Concept {name:'APARCH'})-[r:GENERALIZES_TO]->(sub:Concept)
// RETURN sub.name AS submodel, r.by AS special_case, sub.definition AS description

// Q30: Leverage asymmetry chain — from market observation to trading strategy
// MATCH path = (le:Concept {name:'Leverage Effect (Volatility)'})-[:MOTIVATES|PREREQ_OF*1..4]->(s:Strategy)
// RETURN [n IN nodes(path) | n.name] AS chain, s.description AS strategy_logic

// Q31: EVT tail distribution selection given return series characteristics
// MATCH (mda:Concept {name:'Maximum Domain of Attraction (MDA)'})-[:PREREQ_OF]->(ftt:Concept)-[:PREREQ_OF]->(dist:Concept)
// WHERE dist.category = 'extreme_value_theory'
// RETURN dist.name AS distribution, dist.definition AS selection_criteria

// Q32: Political risk → regime → strategy activation path
// MATCH (pr:Concept {name:'Political Risk'})-[:MOTIVATES]->(pdv:Concept)-[:PREREQ_OF]->(model:Concept)
// RETURN pr.name, pdv.name AS extension, model.name AS vol_model


// =============================================================================
// END v0.6.0
// -----------------------------------------------------------------------------
// CUMULATIVE KG STATS AFTER v0.6.0:
//   Concept nodes      : 201  (173 + 28)
//   Category nodes     : 36   (34 + 2: extreme_value_theory, political_risk)
//   Formula nodes      : 79   (69 + 10)
//   Strategy nodes     : 18   (16 + 2)
//   Regime nodes       : 7    (unchanged)
//   Ticker nodes       : 10   (unchanged)
//   PREREQ_OF edges    : ~290 (~240 + ~50)
//   GENERALIZES_TO     : 22   (13 + 9: APARCH→GARCH/GJR/EGARCH; GEV→subfamilies)
//   MOTIVATES          : 16   (9 + 7)
//   FITTED_TO          : 10   (new relationship type)
//   ACTIVATED_BY       : 38   (33 + 5)
//   CONTRADICTED_BY    : 20   (14 + 6)
//   HAS_FORMULA        : ~115 (~98 + ~17)
//   EVALUATED_BY       : 23   (16 + 7)
//   TRAINED_BY         : 4    (unchanged)
//   TRANSMITS_TO       : 6    (unchanged)
//   MONITORS           : 10   (unchanged)
//   REPLICATES_WITH    : 5    (unchanged)
//   HEDGES             : 4    (unchanged)
//   BELONGS_TO         : ~150 (extended)
// Total relationship types: 17
//   PREREQ_OF, BELONGS_TO, HAS_FORMULA, DERIVED_FROM,
//   ACTIVATED_BY, CONTRADICTED_BY, TRANSMITS_TO, MONITORS,
//   REPLICATES_WITH, HEDGES, GENERALIZES_TO, MOTIVATES,
//   TRAINED_BY, EVALUATED_BY, FITTED_TO,
//   CORRELATED_WITH (runtime), HAS_SIGNAL (runtime)
// New concept domains added in v0.6.0:
//   Extreme Value Theory: POT | BMM | GPD | GEV family (Gumbel/Frechet/Weibull) |
//   Fisher-Tippett Theorem | MDA | GARCH-EVT combination |
//   GPD estimators (MLE, Hill, Moment) | Threshold selection | Mean Excess Function |
//   Block size selection | GEVMLE | GEV-GPD relationship |
//   Asymmetric GARCH: EGARCH | GJR-GARCH | APARCH | Leverage Effect |
//   Innovation Term | APARCH power parameter |
//   Political Risk: 5-component framework | Dummy variable GARCH | Uncertainty Premium |
//   Bagging (Multi-Transformer) | Multi-Head Attention formula completeness
// =============================================================================


// =============================================================================
// v0.7.0 — BAYESIAN NETWORKS FOR FINANCIAL RISK MANAGEMENT
// Sources:
//   - "Reintroduction to Graphs and Networks" (WQU M5L1, Coscia; Kochenderfer)
//   - "The Monty Hall Problem" (WQU M5L2, Galbraith; Schreiber/Pomegranate)
//   - "Sampling and Inference" (WQU M5L3, Xing; Kochenderfer; Kirkley)
//   - "Inference and Sampling in Practice" (WQU M5L4 Project.ipynb, Shenoy & Shenoy 1999)
// New domains: Bayesian Networks, Probabilistic Inference, Approximate Inference,
//   Factor Graphs, Message Passing, Financial Bayesian Risk Models
// -----------------------------------------------------------------------------
// New concepts  : 22
// New categories: 2  (bayesian_networks, probabilistic_inference)
// New formulas  : 4
// New strategies: 1  (Bayesian Macro Risk Signal)
// No new rel type (existing types cover all new edges)
// =============================================================================


// -----------------------------------------------------------------------------
// A. SCHEMA VERSION NOTE
// -----------------------------------------------------------------------------
// Schema version: 0.7.0
// Changelog:
//   0.7.0 — Bayesian Networks: DAG structure, factor/factor graph, CPT,
//            Monty Hall as canonical BN example. Bayesian inference quartet
//            (prior, likelihood, evidence, posterior). Exact inference:
//            Variable Elimination, Factor Product, Factor Marginalization,
//            Factor Conditioning, MPA. Approximate inference: Direct Sampling,
//            Gibbs Sampling, Weighted (Importance) Sampling, Belief Propagation
//            with message passing. Financial BN: Stock Price BN (Shenoy 1999),
//            pgmpy/Pomegranate implementation nodes. KDE and distance matrix
//            as graph-building tools.


// -----------------------------------------------------------------------------
// B. NEW CATEGORY NODES
// -----------------------------------------------------------------------------

MERGE (:Category {name: 'bayesian_networks',       display: 'Bayesian Networks'});
MERGE (:Category {name: 'probabilistic_inference',  display: 'Probabilistic Inference'});


// -----------------------------------------------------------------------------
// C. CONCEPT NODES — BAYESIAN NETWORK STRUCTURE
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Bayesian Network'})
  SET c.definition   = 'Directed Acyclic Graph (DAG) where nodes represent random variables and directed arcs encode conditional dependencies. Joint distribution factorizes as P(x₁,...,xₙ) = ∏P(xᵢ|parents(xᵢ)). Used for probabilistic reasoning, scenario analysis, and risk factor inference. "Special type of network connecting events that influence each other" (Coscia 29).',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L1; WQU M5L2; Coscia 29; Kochenderfer 2022';

MERGE (c:Concept {name: 'Directed Acyclic Graph (DAG)'})
  SET c.definition   = 'Graph with directed edges and no directed cycles. Structural foundation for Bayesian Networks. Encodes conditional independence via d-separation. Topological ordering enables factorization of joint distribution. Acyclic graphs also referred to as trees in some contexts (Kochenderfer).',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L2; Kochenderfer 2022';

MERGE (c:Concept {name: 'Conditional Probability Table (CPT)'})
  SET c.definition   = 'Tabular encoding of P(X|parents(X)) for each node in a Bayesian Network. Rows index values of X; columns index parent configurations. Product of all CPTs (normalized) gives joint distribution. Implemented via TabularCPD in pgmpy.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L2; WQU M5L4; Kochenderfer 2022';

MERGE (c:Concept {name: 'Factor (Probabilistic)'})
  SET c.definition   = 'Real-valued function of a subset of the random variables: φ(x_S) for S ⊆ {X₁,...,Xₙ}. Posterior P(x) = (1/Z)·∏_m fₘ(xₘ). Factors are the building blocks of factor graphs and encode CPTs in Bayesian networks (Galbraith; Mackay).',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L2; Galbraith; Mackay';

MERGE (c:Concept {name: 'Factor Graph'})
  SET c.definition   = 'Bipartite graph where squares represent factors and circles represent random variables; arcs connect each factor to the variables it depends on. Equivalent to but more explicit than a Bayesian Network for expressing conditional independencies. Pomegranate FactorGraph.pyx: CPTs on one side, variable marginals on the other.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L2; Schreiber/Pomegranate; Mackay';

MERGE (c:Concept {name: 'Conditional Independence (BN)'})
  SET c.definition   = 'In a Bayesian Network, X ⊥ Y | Z if Z d-separates X and Y. Enables factorization of joint distribution and reduces computational complexity exponentially. Core structural property that makes BN inference tractable.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L1; Kochenderfer 2022';

MERGE (c:Concept {name: 'Joint Probability Factorization'})
  SET c.definition   = 'P(x₁,...,xₙ) = ∏ᵢ P(xᵢ|parents(xᵢ)). Chain rule applied to DAG structure. Each variable only depends on its direct parents, not all predecessors. Exploited by Variable Elimination to reduce computational cost from exponential to polynomial in graph width.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Xing CMU lecture 4';

MERGE (c:Concept {name: 'Monty Hall Problem (BN)'})
  SET c.definition   = 'Canonical 3-node Bayesian Network: C (contestant choice), X (prize location), H (host door opened). P(C,X,H) = P(C)·P(X)·P(H|C,X). Query: P(X|C=c, H=h). Counterintuitive answer — switching wins with probability 2/3 — emerges naturally from BN inference. Structural simplicity makes it ideal for teaching.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L2; Galbraith GitHub';

MERGE (c:Concept {name: 'Distance Matrix (Graph)'})
  SET c.definition   = 'Euclidean distance matrix A where Aᵢⱼ = dᵢⱼ². Constructed from correlation matrix: dᵢⱼ = √(2(1-ρᵢⱼ)). Interoperable with graph adjacency matrix (Coscia 68). Foundation for Minimum Spanning Tree construction and correlation network visualization.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L1; Coscia 68; Guo et al. 2018';

MERGE (c:Concept {name: 'Kernel Density Estimation (KDE)'})
  SET c.definition   = 'Non-parametric density estimator: f̂(x) = (1/nh)·Σ K((x-xᵢ)/h). Bandwidth h controls smoothing: too small → undersmoothing (noisy); too large → oversmoothing (loss of structure). Used to estimate empirical distributions for BN node parameters and portfolio return distributions.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L1; Akinshin 2020';


// -----------------------------------------------------------------------------
// D. CONCEPT NODES — BAYESIAN INFERENCE QUARTET
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Prior Probability'})
  SET c.definition   = 'P(θ): probability distribution over model parameters before observing data. Represents initial belief about hypothesis θ. Can be informative (based on domain knowledge) or non-informative. Can be informed by frequentist methods — Bayesian and frequentist priors are not mutually exclusive (Jihan).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Jihan WSO2';

MERGE (c:Concept {name: 'Likelihood (Bayesian)'})
  SET c.definition   = 'P(X|θ): conditional probability of observed data X given parameter set θ. In inference context: marginal probability of a subset of variables conditioned on evidence. Provides the "data-driven" update to the prior. L(θ;X) is the likelihood function (Xing 1).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Xing CMU lecture 4 p.1';

MERGE (c:Concept {name: 'Evidence (Bayesian)'})
  SET c.definition   = 'P(X): marginal probability of observed data, integrating over all hypotheses: P(X) = ∫ P(X|θ)·P(θ)dθ. Acts as normalizing constant in Bayes theorem. "Summation of probabilities of all possible hypotheses weighted by their likelihood" (Jihan). Often intractable analytically — motivation for approximate inference.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Jihan WSO2';

MERGE (c:Concept {name: 'Posterior Probability'})
  SET c.definition   = 'P(θ|X): conditional distribution of parameters after observing data. P(θ|X) ∝ P(X|θ)·P(θ). In BN inference: "posteriori belief" = conditional probability distribution of query nodes conditioned on evidence. Maximizing gives MPA (Xing 4).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Jihan WSO2; Xing CMU lecture 4';


// -----------------------------------------------------------------------------
// E. CONCEPT NODES — EXACT INFERENCE
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Variable Elimination (VE)'})
  SET c.definition   = 'Exact inference algorithm for BNs: eliminates variables one at a time by marginalizing (summing out) irrelevant factors. Complexity exponential in tree-width of graph. Steps: factor product → factor marginalization, repeated for each eliminated variable. Kochenderfer pp.45-46.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Xing CMU lecture 4; Kochenderfer 2022 pp.45-46';

MERGE (c:Concept {name: 'Factor Product'})
  SET c.definition   = 'Multiplication of two factors sharing variables: (φ₁·φ₂)(x) = φ₁(x_S₁)·φ₂(x_S₂). Scope of product = union of scopes. First step in Variable Elimination. "Not all terms have a dependence on all variables" — key insight enabling efficient computation (Kochenderfer).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kochenderfer 2022';

MERGE (c:Concept {name: 'Factor Marginalization'})
  SET c.definition   = 'Summing out a variable from a factor: (Σ_x φ)(y) = Σ_x φ(x,y). Reduces factor scope by one variable. Second step in Variable Elimination. Equivalent to marginalizing joint distribution — "relieves us of having to calculate the higher-dimensional distribution" (Xing 4).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Xing CMU lecture 4 p.1-2';

MERGE (c:Concept {name: 'Factor Conditioning'})
  SET c.definition   = 'Fixing observed variables to their evidence values within a factor. Reduces factor to a sub-table consistent with evidence. Kochenderfer p.44: inferring a conditional probability by conditioning on "temporary assumption inconsistent with evidence." Used before Factor Product in VE.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kochenderfer 2022 p.44';

MERGE (c:Concept {name: 'Most Probable Assignment (MPA)'})
  SET c.definition   = 'argmax_{θ} P(θ|X): the parameter/variable assignment maximizing posterior probability. "Most probable assignment" in BN context. Also called MAP (Maximum A Posteriori). Used to find most likely market regime or risk scenario given observed data (Xing 4).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Xing CMU lecture 4 p.1';


// -----------------------------------------------------------------------------
// F. CONCEPT NODES — APPROXIMATE INFERENCE & MESSAGE PASSING
// -----------------------------------------------------------------------------

MERGE (c:Concept {name: 'Belief Propagation'})
  SET c.definition   = 'Inference algorithm = VE + message passing. "Messages" are intermediate factor tables shared across multiple queries. Avoids redundant computation: same messages reused for different queries on same graph. Efficient on trees; approximate (Loopy BP) on graphs with cycles (Kirkley; Xing lecture 13).',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kirkley et al. Science; Xing CMU lecture 13';

MERGE (c:Concept {name: 'Message Passing'})
  SET c.definition   = 'Core mechanism in Belief Propagation: each node sends "messages" to neighbors containing marginal information. Messages = solutions to self-consistent equations solved by numerical iteration (Kirkley 1). Sharing messages across queries avoids recomputing intermediate distributions. Enables O(n) complexity on trees.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kirkley et al.; Stratos';

MERGE (c:Concept {name: 'Direct Sampling'})
  SET c.definition   = 'Approximate inference by drawing samples from prior distribution in topological order. Each variable sampled from P(xᵢ|sampled_parents). Simple but inefficient for rare evidence events — many samples wasted on inconsistent configurations. Foundation for more advanced sampling methods.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kochenderfer 2022';

MERGE (c:Concept {name: 'Gibbs Sampling'})
  SET c.definition   = 'MCMC approximate inference: initialise all variables, then iteratively resample each variable from its conditional distribution given current values of all others P(xᵢ|x_{-i}). Converges to true joint distribution. Efficient when full conditional is tractable. Used in large financial BNs.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kochenderfer 2022';

MERGE (c:Concept {name: 'Weighted Sampling (Importance Sampling)'})
  SET c.definition   = 'Approximate inference: sample from prior, weight each sample by likelihood of evidence. Ê[f] = Σᵢ wᵢ·f(xᵢ) / Σᵢ wᵢ where wᵢ = P(evidence|xᵢ). More efficient than Direct Sampling for conditioning on rare events. Weights correct for prior-evidence mismatch.',
      c.category     = 'probabilistic_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L3; Kochenderfer 2022';

MERGE (c:Concept {name: 'Stock Price Bayesian Network'})
  SET c.definition   = 'Shenoy & Shenoy (1999) financial BN: Interest_Rate → Stock_Market → Stock_Price ← Oil_Industry. CPDs: P(IR=high)=0.75; P(SM=good|IR=low)=0.80, P(SM=good|IR=high)=0.30. Unconditional P(SP=high)=0.626. Conditioning on IR=high triggers sell signal when P(SP=low)>0.35 threshold. Prototype for financial BN risk modeling.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L4; Shenoy & Shenoy 1999 Computational Finance';

MERGE (c:Concept {name: 'pgmpy Library'})
  SET c.definition   = 'Python probabilistic graphical models library. Key classes: DiscreteBayesianNetwork (DAG structure), TabularCPD (conditional probability tables), VariableElimination (exact inference). check_model() validates CPD consistency. Used in M5L4 financial BN implementation.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M5L4; pgmpy GitHub';


// -----------------------------------------------------------------------------
// G. CATEGORY MEMBERSHIP — v0.7.0
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Bayesian Network'}),                    (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Directed Acyclic Graph (DAG)'}),        (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Conditional Probability Table (CPT)'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Factor (Probabilistic)'}),              (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Factor Graph'}),                        (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Conditional Independence (BN)'}),       (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Joint Probability Factorization'}),     (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Monty Hall Problem (BN)'}),             (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Distance Matrix (Graph)'}),             (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Stock Price Bayesian Network'}),        (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'pgmpy Library'}),                       (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Kernel Density Estimation (KDE)'}),     (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Prior Probability'}),                   (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Likelihood (Bayesian)'}),               (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Evidence (Bayesian)'}),                 (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Posterior Probability'}),               (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Variable Elimination (VE)'}),           (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Factor Product'}),                      (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Factor Marginalization'}),              (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Factor Conditioning'}),                 (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Most Probable Assignment (MPA)'}),      (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Belief Propagation'}),                  (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Message Passing'}),                     (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Direct Sampling'}),                     (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Gibbs Sampling'}),                      (cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Weighted Sampling (Importance Sampling)'}),(cat:Category {name:'probabilistic_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);


// -----------------------------------------------------------------------------
// H. PREREQUISITE CHAINS — v0.7.0
// -----------------------------------------------------------------------------

// BN structure prerequisites
MATCH (a:Concept {name:'Directed Acyclic Graph (DAG)'}),         (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Probability Table (CPT)'}),  (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor (Probabilistic)'}),               (b:Concept {name:'Factor Graph'})                      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Graph'}),                         (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Independence (BN)'}),        (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Joint Probability Factorization'}),      (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Probability Table (CPT)'}),  (b:Concept {name:'Factor (Probabilistic)'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Directed Acyclic Graph (DAG)'}),         (b:Concept {name:'Joint Probability Factorization'})   MERGE (a)-[:PREREQ_OF]->(b);

// Inference quartet chain
MATCH (a:Concept {name:'Prior Probability'}),                    (b:Concept {name:'Posterior Probability'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Likelihood (Bayesian)'}),                (b:Concept {name:'Posterior Probability'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Evidence (Bayesian)'}),                  (b:Concept {name:'Posterior Probability'})             MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Posterior Probability'}),                (b:Concept {name:'Most Probable Assignment (MPA)'})    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}),                     (b:Concept {name:'Posterior Probability'})             MERGE (a)-[:PREREQ_OF]->(b);

// Exact inference chain
MATCH (a:Concept {name:'Joint Probability Factorization'}),      (b:Concept {name:'Variable Elimination (VE)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Product'}),                       (b:Concept {name:'Variable Elimination (VE)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Marginalization'}),               (b:Concept {name:'Variable Elimination (VE)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Conditioning'}),                  (b:Concept {name:'Variable Elimination (VE)'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor (Probabilistic)'}),               (b:Concept {name:'Factor Product'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor (Probabilistic)'}),               (b:Concept {name:'Factor Marginalization'})            MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor (Probabilistic)'}),               (b:Concept {name:'Factor Conditioning'})               MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variable Elimination (VE)'}),            (b:Concept {name:'Belief Propagation'})                MERGE (a)-[:PREREQ_OF]->(b);

// Approximate inference chain
MATCH (a:Concept {name:'Message Passing'}),                      (b:Concept {name:'Belief Propagation'})                MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Direct Sampling'}),                      (b:Concept {name:'Gibbs Sampling'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Direct Sampling'}),                      (b:Concept {name:'Weighted Sampling (Importance Sampling)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Prior Probability'}),                    (b:Concept {name:'Direct Sampling'})                   MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Likelihood (Bayesian)'}),                (b:Concept {name:'Weighted Sampling (Importance Sampling)'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Evidence (Bayesian)'}),                  (b:Concept {name:'Weighted Sampling (Importance Sampling)'}) MERGE (a)-[:PREREQ_OF]->(b);

// Financial BN chain
MATCH (a:Concept {name:'Bayesian Network'}),                     (b:Concept {name:'Monty Hall Problem (BN)'})           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}),                     (b:Concept {name:'Stock Price Bayesian Network'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Variable Elimination (VE)'}),            (b:Concept {name:'Stock Price Bayesian Network'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'pgmpy Library'}),                        (b:Concept {name:'Stock Price Bayesian Network'})      MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Probability Table (CPT)'}),  (b:Concept {name:'Stock Price Bayesian Network'})      MERGE (a)-[:PREREQ_OF]->(b);

// Graph ↔ distance matrix ↔ BN connection
MATCH (a:Concept {name:'Distance Matrix (Graph)'}),              (b:Concept {name:'Financial Network'})                 MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Kernel Density Estimation (KDE)'}),      (b:Concept {name:'Prior Probability'})                 MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Kernel Density Estimation (KDE)'}),      (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Distance Matrix (Graph)'}),              (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain: BN → systemic risk
MATCH (a:Concept {name:'Bayesian Network'}),                     (b:Concept {name:'Systemic Risk Measurement'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}),                     (b:Concept {name:'Stress Testing'})                    MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Posterior Probability'}),                (b:Concept {name:'Scenario Analysis'})                 MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Belief Propagation'}),                   (b:Concept {name:'Contagion'})                         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),                     (b:Concept {name:'Prior Probability'})                 MERGE (a)-[:PREREQ_OF]->(b);

// Cross-domain: BN inference → VaR / Deep Learning
MATCH (a:Concept {name:'Bayesian Network'}),                     (b:Concept {name:'DeepVaR'})                           MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Gibbs Sampling'}),                       (b:Concept {name:'Probabilistic Forecasting'})         MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Most Probable Assignment (MPA)'}),       (b:Concept {name:'Regime Detector'})                   MERGE (a)-[:PREREQ_OF]->(b);


// -----------------------------------------------------------------------------
// I. MOTIVATES — BAYESIAN NETWORK MOTIVATION LINKS
// -----------------------------------------------------------------------------

MATCH (a:Concept {name:'Evidence (Bayesian)'}),                  (b:Concept {name:'Weighted Sampling (Importance Sampling)'}) MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Evidence (Bayesian)'}),                  (b:Concept {name:'Gibbs Sampling'})                    MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Conditional Independence (BN)'}),        (b:Concept {name:'Variable Elimination (VE)'})         MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Non-Stationarity'}),                     (b:Concept {name:'Bayesian Network'})                  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Fat Tails'}),                            (b:Concept {name:'Kernel Density Estimation (KDE)'})   MERGE (a)-[:MOTIVATES]->(b);


// -----------------------------------------------------------------------------
// J. FORMULA NODES — v0.7.0
// -----------------------------------------------------------------------------

UNWIND [
  {id: 'f_bayes', name: 'Bayes Theorem', expression: 'P(θ|X) = P(X|θ)·P(θ) / P(X)', latex: 'P(\\theta|X) = \\frac{P(X|\\theta)\\,P(\\theta)}{P(X)}', params: ['θ','X'], note: 'P(θ)=prior; P(X|θ)=likelihood; P(X)=evidence (normalizing constant); P(θ|X)=posterior', output: 'posterior_distribution'},
  {id: 'f_factor_posterior', name: 'Factor Graph Posterior', expression: 'P(x) = (1/Z) · ∏ₘ fₘ(xₘ)', latex: 'P(\\mathbf{x}) \\equiv \\frac{1}{Z}P^*(\\mathbf{x}) = \\frac{1}{Z}\\prod_{m=1}^{M}f_m(\\mathbf{x}_m)', params: ['Z','fₘ','xₘ'], note: 'Z=partition function (normalizing constant); fₘ=factor m; product over all M factors', output: 'posterior_distribution'},
  {id: 'f_bn_factorization', name: 'Bayesian Network Joint Factorization', expression: 'P(x₁,...,xₙ) = ∏ᵢ P(xᵢ | parents(xᵢ))', latex: 'P(x_1,\\ldots,x_n) = \\prod_{i=1}^{n} P\\!\\left(x_i \\mid \\text{pa}(x_i)\\right)', params: ['xᵢ','parents(xᵢ)'], note: 'Chain rule on DAG topology; each node depends only on direct parents', output: 'joint_probability'},
  {id: 'f_kde', name: 'Kernel Density Estimator', expression: 'f̂(x) = (1/(n·h)) · Σᵢ K((x - xᵢ)/h)', latex: '\\hat{f}(x) = \\frac{1}{nh}\\sum_{i=1}^{n}K\\!\\left(\\frac{x-x_i}{h}\\right)', params: ['n','h','K','xᵢ'], note: 'h=bandwidth (smoothing parameter); K=kernel function (e.g. Gaussian); bias-variance tradeoff in h', output: 'density_estimate'}
] AS data
MERGE (f:Formula {id: data.id})
SET f.name = data.name,
    f.expression = data.expression,
    f.latex = data.latex,
    f.params = data.params,
    f.note = data.note,
    f.output = data.output
RETURN count(f) AS formulas_processed;

// -----------------------------------------------------------------------------
// K. CONCEPT → FORMULA RELATIONSHIPS (v0.7.0)
// -----------------------------------------------------------------------------

MATCH (c:Concept {name:'Posterior Probability'}),               (f:Formula {id:'f_bayes'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Prior Probability'}),                   (f:Formula {id:'f_bayes'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Likelihood (Bayesian)'}),               (f:Formula {id:'f_bayes'})              MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Factor Graph'}),                        (f:Formula {id:'f_factor_posterior'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Factor (Probabilistic)'}),              (f:Formula {id:'f_factor_posterior'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Bayesian Network'}),                    (f:Formula {id:'f_bn_factorization'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Joint Probability Factorization'}),     (f:Formula {id:'f_bn_factorization'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Conditional Independence (BN)'}),       (f:Formula {id:'f_bn_factorization'})   MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Kernel Density Estimation (KDE)'}),     (f:Formula {id:'f_kde'})               MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Variable Elimination (VE)'}),           (f:Formula {id:'f_bn_factorization'})   MERGE (c)-[:HAS_FORMULA]->(f);


// -----------------------------------------------------------------------------
// L. STRATEGY NODE — v0.7.0
// -----------------------------------------------------------------------------

MERGE (s:Strategy {name: 'Bayesian Macro Risk Signal'})
  SET s.derived_from         = 'Bayesian Network',
      s.description          = 'Build a 4-node Bayesian Network (Interest_Rate → Stock_Market → Stock_Price ← Oil_Price) calibrated on rolling 252-day data. Run VariableElimination daily: query P(Stock_Price=high | observed_macro_signals). If posterior P(down) > 0.35 threshold → reduce gross exposure by 20%. Regime state encoded as MPA of hidden nodes.',
      s.formula_ref          = 'f_bayes',
      s.sizing_formula_ref   = 'f_kelly',
      s.param_lookback       = 252,
      s.param_sell_threshold = 0.35,
      s.param_exposure_cut   = 0.20,
      s.param_inference_algo = 'VariableElimination',
      s.risk_weight          = 0.80,
      s.strategy_type        = 'overlay',
      s.status               = 'active',
      s.target_ticker      = 'SPY';

MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (c:Concept {name:'Bayesian Network'})               MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (c:Concept {name:'Variable Elimination (VE)'})      MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (c:Concept {name:'Stock Price Bayesian Network'})   MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (c:Concept {name:'Posterior Probability'})          MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (f:Formula {id:'f_bayes'})                          MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (f:Formula {id:'f_bn_factorization'})               MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (f:Formula {id:'f_kelly'})                          MERGE (s)-[:HAS_FORMULA]->(f);

MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (r:Regime {name:'HighVolatility'})   MERGE (s)-[:ACTIVATED_BY {weight:0.90}]->(r);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (r:Regime {name:'Crisis'})           MERGE (s)-[:ACTIVATED_BY {weight:1.00}]->(r);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (r:Regime {name:'SystemicStress'})   MERGE (s)-[:ACTIVATED_BY {weight:0.85}]->(r);

MATCH (a:Strategy {name:'Bayesian Macro Risk Signal'}), (b:Strategy {name:'GARCH-EVT VaR Overlay'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Both are macro-driven overlay strategies that scale down exposure; running both simultaneously over-constrains position limits and double-penalises adverse macro signals'}]->(b);


// -----------------------------------------------------------------------------
// M. NEW AGENT QUERY PATTERNS (v0.7.0)
// -----------------------------------------------------------------------------

// Q33: Full Bayesian inference pipeline for a financial risk BN
// MATCH path = (prior:Concept {name:'Prior Probability'})-[:PREREQ_OF*1..4]->(mpa:Concept {name:'Most Probable Assignment (MPA)'})
// RETURN [n IN nodes(path) | n.name] AS inference_pipeline

// Q34: VE vs Belief Propagation trade-off for a given graph structure
// MATCH (ve:Concept {name:'Variable Elimination (VE)'})-[:PREREQ_OF]->(bp:Concept {name:'Belief Propagation'})
// MATCH (ve)-[:HAS_FORMULA]->(f:Formula)
// RETURN ve.definition AS exact_method, bp.definition AS efficient_method, f.expression AS key_formula

// Q35: All approximate inference methods and their motivations
// MATCH (problem:Concept)-[:MOTIVATES]->(approx:Concept)
// WHERE approx.category = 'probabilistic_inference' AND approx.difficulty = 'advanced'
// RETURN problem.name AS bottleneck, approx.name AS solution, approx.definition AS mechanism

// Q36: Bayesian strategy activation map — which regimes trigger macro BN overlay
// MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'})-[a:ACTIVATED_BY]->(r:Regime)
// RETURN r.name AS regime, a.weight AS activation_strength ORDER BY a.weight DESC

// Q37: Financial BN construction path — from raw data to inference result
// MATCH path = (kde:Concept {name:'Kernel Density Estimation (KDE)'})-[:PREREQ_OF*1..5]->(mpa:Concept {name:'Most Probable Assignment (MPA)'})
// RETURN [n IN nodes(path) | n.name] AS construction_pipeline

// Q38: Cross-domain: how Bayesian Networks connect to systemic risk concepts
// MATCH (bn:Concept {name:'Bayesian Network'})-[:PREREQ_OF]->(risk:Concept)
// WHERE risk.category IN ['systemic_risk','risk_metrics']
// RETURN risk.name AS downstream_risk_concept, risk.definition AS application


// =============================================================================
// END v0.7.0
// -----------------------------------------------------------------------------
// CUMULATIVE KG STATS AFTER v0.7.0:
//   Concept nodes      : 223  (201 + 22)
//   Category nodes     : 38   (36 + 2: bayesian_networks, probabilistic_inference)
//   Formula nodes      : 83   (79 + 4)
//   Strategy nodes     : 19   (18 + 1)
//   Regime nodes       : 7    (unchanged)
//   Ticker nodes       : 10   (unchanged)
//   PREREQ_OF edges    : ~335 (~290 + ~45)
//   ACTIVATED_BY edges : 41   (38 + 3)
//   CONTRADICTED_BY    : 21   (20 + 1)
//   HAS_FORMULA        : ~125 (~115 + 10)
//   MOTIVATES          : 21   (16 + 5)
//   GENERALIZES_TO     : 22   (unchanged)
//   FITTED_TO          : 10   (unchanged)
//   EVALUATED_BY       : 23   (unchanged)
//   TRAINED_BY         : 4    (unchanged)
//   BELONGS_TO         : ~175 (extended)
//   TRANSMITS_TO       : 6    (unchanged)
//   MONITORS           : 10   (unchanged)
// Total relationship types: 17  (unchanged — no new rel types this version)
// New concept domains added in v0.7.0:
//   Bayesian Network structure: DAG | CPT | Factor | Factor Graph |
//   Conditional Independence | Joint Factorization | Monty Hall BN |
//   Distance Matrix | Stock Price BN | pgmpy |
//   Bayesian Inference: Prior | Likelihood | Evidence | Posterior | MPA |
//   Exact Inference: VE | Factor Product | Factor Marginalization | Factor Conditioning |
//   Approximate Inference: Belief Propagation | Message Passing |
//   Direct Sampling | Gibbs Sampling | Weighted/Importance Sampling |
//   KDE for density estimation
// =============================================================================

// =============================================================================
// v0.8.0 — BAYESIAN NETWORK STRUCTURE LEARNING
// Sources: WQU M6L4 (Project.ipynb); "Going Deeper with Bayesian Nets";
//          "K2: Learning Bayesian Network Structure";
//          "How to Learn the Structure of a Network"
// New concepts: 28 | New formulas: 5 | New strategies: 1
// New categories: structure_learning, dynamic_bayesian_networks
// =============================================================================

// ── Categories ────────────────────────────────────────────────────────────────
MERGE (cat:Category {name: 'structure_learning'})
  SET cat.label = 'BN Structure Learning';
MERGE (cat:Category {name: 'dynamic_bayesian_networks'})
  SET cat.label = 'Dynamic Bayesian Networks';

// ── Concepts: BN Advanced Topology ───────────────────────────────────────────
MERGE (c:Concept {name: 'D-Separation'})
  SET c.definition   = 'Graphical criterion for determining conditional independence between sets of variables in a Bayesian network; X and Y are d-separated by Z if every path between them is blocked by Z.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M6; Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Markov Blanket'})
  SET c.definition   = 'The minimal set of nodes that renders a node conditionally independent of all other nodes in the network; consists of the node\'s parents, children, and co-parents (other parents of its children).',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M6; Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Active Path'})
  SET c.definition   = 'A path between two nodes in a BN that is not blocked by any observed evidence; determines whether information can flow between variables.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Explaining Away'})
  SET c.definition   = 'Inter-causal reasoning: observing one cause of an effect makes alternative causes less probable; arises at v-structures (colliders) in a DAG.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'V-Structure'})
  SET c.definition   = 'A collider pattern A → C ← B in a DAG where two parents share a child with no direct edge between them; creates the explaining-away phenomenon.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Naive Bayes Classifier'})
  SET c.definition   = 'Simplified BN where a class variable is the sole parent of all feature variables; assumes features are conditionally independent given the class. Effective for text classification and rapid signal filtering.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Plate Notation'})
  SET c.definition   = 'Compact graphical representation of BNs with repeated structure; a plate (rectangle) indicates that the enclosed nodes are replicated for each element of an index set (e.g., observations, assets).',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Hidden Markov Model'})
  SET c.definition   = 'Dynamic BN with a latent Markov chain (hidden states) and observed emissions; each hidden state depends only on the previous (Markov property) and each observation depends only on its contemporaneous hidden state.',
      c.category     = 'dynamic_bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Dynamic Bayesian Network'})
  SET c.definition   = 'BN extended over time by adding temporal edges (transition arcs) between time slices; encodes the joint distribution of a multivariate time series under conditional independence assumptions.',
      c.category     = 'dynamic_bayesian_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Transition Model'})
  SET c.definition   = 'Conditional distribution P(X_t | X_{t-1}) specifying how hidden states evolve over time in a Dynamic BN or HMM.',
      c.category     = 'dynamic_bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets';

MERGE (c:Concept {name: 'Emission Model'})
  SET c.definition   = 'Conditional distribution P(O_t | X_t) linking latent states to observed variables in an HMM; parameterizes how observations are generated from hidden states.',
      c.category     = 'dynamic_bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets';

// ── Concepts: Structure Learning ──────────────────────────────────────────────
MERGE (c:Concept {name: 'Structure Learning'})
  SET c.definition   = 'Process of discovering the DAG topology of a Bayesian network from observed data; two main paradigms: score-based search and constraint-based search.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'WQU M6L4; K2 Learning BN Structure; How to Learn the Structure of a Network';

MERGE (c:Concept {name: 'Score-Based Structure Learning'})
  SET c.definition   = 'Approach to BN structure learning that assigns a score (e.g., K2, BIC, BDeu) to each candidate DAG and searches the space of DAGs to maximize the score.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network; WQU M6L4';

MERGE (c:Concept {name: 'Constraint-Based Structure Learning'})
  SET c.definition   = 'Approach to BN structure learning that performs conditional independence tests (e.g., PC algorithm, FCI) to identify d-separation relationships and recover the skeleton and edge orientations.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network';

MERGE (c:Concept {name: 'K2 Algorithm'})
  SET c.definition   = 'Greedy score-based structure learning algorithm that assumes a fixed topological ordering of nodes and greedily adds parents to each node to maximize the K2 score; polynomial complexity given the ordering.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'K2 Learning BN Structure; WQU M6L4; Cooper & Herskovits 1992';

MERGE (c:Concept {name: 'K2 Score'})
  SET c.definition   = 'Bayesian structure score based on a Dirichlet prior with unit hyperparameters; proportional to the log-marginal likelihood of the data given the graph structure assuming multinomial CPDs and uniform priors.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'K2 Learning BN Structure; Cooper & Herskovits 1992';

MERGE (c:Concept {name: 'BIC Score'})
  SET c.definition   = 'Bayesian Information Criterion adapted for BN structure scoring; penalizes model complexity (number of parameters) relative to log-likelihood, preventing overfitting in structure search.',
      c.category     = 'structure_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network; WQU M6L4';

MERGE (c:Concept {name: 'BDeu Score'})
  SET c.definition   = 'Bayesian Dirichlet equivalent uniform score; a Bayesian score for BN structures that assigns equivalent sample sizes uniformly across parent configurations, ensuring score equivalence for Markov-equivalent graphs.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network; WQU M6L4; Heckerman et al. 1995';

MERGE (c:Concept {name: 'BDs Score'})
  SET c.definition   = 'Bayesian Dirichlet sparse score; variant of BDeu that handles sparse data more robustly by using non-uniform equivalent sample size allocation across parent configurations.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network; WQU M6L4';

MERGE (c:Concept {name: 'Hill Climb Search'})
  SET c.definition   = 'Greedy local search algorithm for BN structure learning; starts from an empty (or random) DAG and iteratively adds, removes, or reverses edges to maximize the chosen structure score until no improvement is possible.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'How to Learn the Structure of a Network; WQU M6L4; pgmpy HillClimbSearch';

MERGE (c:Concept {name: 'Maximum Likelihood Estimator'})
  SET c.definition   = 'Parameter estimation method for BN CPDs that sets probabilities equal to empirical relative frequencies in the training data; maximizes P(data | model).',
      c.category     = 'structure_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'WQU M6L4; pgmpy MaximumLikelihoodEstimator';

MERGE (c:Concept {name: 'Bayesian Parameter Estimation'})
  SET c.definition   = 'CPD estimation using a Dirichlet prior over multinomial parameters; produces posterior mean estimates that regularize towards the prior, avoiding zero-probability issues in sparse data.',
      c.category     = 'structure_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network; WQU M6L4';

MERGE (c:Concept {name: 'Equivalence Class'})
  SET c.definition   = 'Set of DAGs that encode the same conditional independence assertions and are therefore indistinguishable from observational data alone; represented by a Completed Partially Directed Acyclic Graph (CPDAG).',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network';

MERGE (c:Concept {name: 'CPDAG'})
  SET c.definition   = 'Completed Partially Directed Acyclic Graph; canonical representation of a Markov equivalence class where directed edges are those with a fixed orientation in all member DAGs and undirected edges are those that can be reversed.',
      c.category     = 'structure_learning',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'How to Learn the Structure of a Network';

MERGE (c:Concept {name: 'Topological Ordering'})
  SET c.definition   = 'A linear ordering of DAG nodes such that for every directed edge u → v, u appears before v; required as input for the K2 algorithm to constrain the search space.',
      c.category     = 'structure_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'K2 Learning BN Structure';

MERGE (c:Concept {name: 'BN Simulation'})
  SET c.definition   = 'Generation of synthetic data by ancestral sampling from a fully parameterized Bayesian network; used to validate structure and parameter learning by comparing learned model to the ground-truth data-generating process.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M6L4; pgmpy simulate()';

MERGE (c:Concept {name: 'Domain Knowledge Constraint'})
  SET c.definition   = 'Expert-specified restriction on the structure search space (e.g., fixing edge direction using causal domain knowledge); used to break Markov equivalence ambiguities that data alone cannot resolve.',
      c.category     = 'structure_learning',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M6L4; How to Learn the Structure of a Network';

MERGE (c:Concept {name: 'Ancestral Sampling'})
  SET c.definition   = 'Forward sampling procedure for BNs: sample root nodes first from marginals, then sample each child from its CPD conditioned on already-sampled parents, following topological order.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Going Deeper with Bayesian Nets; WQU M6L4';

// ── Formula nodes ─────────────────────────────────────────────────────────────
UNWIND [
  {id: 'f_k2_score', name: 'K2 Structure Score', expression: 'Score_K2(G,D) = Σ_i Σ_j [ log(Γ(α_ij)/Γ(α_ij+N_ij)) + Σ_k log(Γ(α_ijk+N_ijk)/Γ(α_ijk)) ]', latex: 'f(x_i,\\Pi_i,D)=\\prod_{j=1}^{q_i}\\frac{(r_i-1)!}{(N_{ij}+r_i-1)!}\\prod_{k=1}^{r_i}N_{ijk}!', params: ['r_i','q_i','N_ijk','alpha_ijk'], output: 'structure_score'},
  {id: 'f_bic_score', name: 'BIC Structure Score', expression: 'BIC(G,D) = log P(D|G,θ_MLE) - (d/2)·log(N)', latex: '\\text{BIC}(G,D)=\\ell(\\hat{\\theta}|D,G)-\\frac{d}{2}\\ln N', params: ['log_likelihood','d','N'], output: 'penalized_structure_score'},
  {id: 'f_bdeu_score', name: 'BDeu Structure Score', expression: 'BDeu(G,D) = Σ_i Σ_j [ logΓ(α/q_i) - logΓ(α/q_i + N_ij) + Σ_k logΓ(α/(q_i·r_i) + N_ijk) - logΓ(α/(q_i·r_i)) ]', latex: '\\sum_i\\sum_j\\left[\\log\\frac{\\Gamma(\\alpha/q_i)}{\\Gamma(\\alpha/q_i+N_{ij})}+\\sum_k\\log\\frac{\\Gamma(\\alpha/(q_i r_i)+N_{ijk})}{\\Gamma(\\alpha/(q_i r_i))}\\right]', params: ['alpha','q_i','r_i','N_ijk'], output: 'bayesian_structure_score'},
  {id: 'f_mle_cpd', name: 'MLE CPD Estimate', expression: 'θ_ijk = N_ijk / N_ij', latex: '\\hat{\\theta}_{ijk}=\\frac{N_{ijk}}{N_{ij}}', params: ['N_ijk','N_ij'], output: 'conditional_probability'},
  {id: 'f_hmm_joint', name: 'HMM Joint Distribution', expression: 'P(X_{1:T},O_{1:T}) = P(X_1)·Π_t P(X_t|X_{t-1})·P(O_t|X_t)', latex: 'P(X_{1:T},O_{1:T})=P(X_1)\\prod_{t=2}^T P(X_t|X_{t-1})\\prod_{t=1}^T P(O_t|X_t)', params: ['X_t','O_t','T'], output: 'joint_probability_sequence'}
] AS data
MERGE (f:Formula {id: data.id})
SET f.name = data.name,
    f.expression = data.expression,
    f.latex = data.latex,
    f.params = data.params,
    f.output = data.output
RETURN count(f) AS formulas_processed;

// ── BELONGS_TO ────────────────────────────────────────────────────────────────
MATCH (c:Concept {name:'D-Separation'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Markov Blanket'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Active Path'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Explaining Away'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'V-Structure'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Naive Bayes Classifier'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Plate Notation'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BN Simulation'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Ancestral Sampling'}), (cat:Category {name:'bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Hidden Markov Model'}), (cat:Category {name:'dynamic_bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Dynamic Bayesian Network'}), (cat:Category {name:'dynamic_bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Transition Model'}), (cat:Category {name:'dynamic_bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Emission Model'}), (cat:Category {name:'dynamic_bayesian_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Structure Learning'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Score-Based Structure Learning'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Constraint-Based Structure Learning'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'K2 Algorithm'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'K2 Score'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BIC Score'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BDeu Score'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BDs Score'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Hill Climb Search'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Maximum Likelihood Estimator'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Bayesian Parameter Estimation'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Equivalence Class'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'CPDAG'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Topological Ordering'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Domain Knowledge Constraint'}), (cat:Category {name:'structure_learning'}) MERGE (c)-[:BELONGS_TO]->(cat);

// ── HAS_FORMULA ───────────────────────────────────────────────────────────────
MATCH (c:Concept {name:'K2 Algorithm'}), (f:Formula {id:'f_k2_score'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'K2 Score'}), (f:Formula {id:'f_k2_score'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'BIC Score'}), (f:Formula {id:'f_bic_score'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'BDeu Score'}), (f:Formula {id:'f_bdeu_score'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Maximum Likelihood Estimator'}), (f:Formula {id:'f_mle_cpd'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Hidden Markov Model'}), (f:Formula {id:'f_hmm_joint'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Dynamic Bayesian Network'}), (f:Formula {id:'f_hmm_joint'}) MERGE (c)-[:HAS_FORMULA]->(f);

// ── PREREQ_OF ─────────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'D-Separation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Independence'}), (b:Concept {name:'D-Separation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DAG'}), (b:Concept {name:'D-Separation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'D-Separation'}), (b:Concept {name:'Markov Blanket'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'V-Structure'}), (b:Concept {name:'Explaining Away'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DAG'}), (b:Concept {name:'V-Structure'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Naive Bayes Classifier'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Independence'}), (b:Concept {name:'Naive Bayes Classifier'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Plate Notation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Dynamic Bayesian Network'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Dynamic Bayesian Network'}), (b:Concept {name:'Hidden Markov Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Transition Model'}), (b:Concept {name:'Hidden Markov Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Emission Model'}), (b:Concept {name:'Hidden Markov Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Structure Learning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DAG'}), (b:Concept {name:'Structure Learning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Structure Learning'}), (b:Concept {name:'Score-Based Structure Learning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Structure Learning'}), (b:Concept {name:'Constraint-Based Structure Learning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'D-Separation'}), (b:Concept {name:'Constraint-Based Structure Learning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Score-Based Structure Learning'}), (b:Concept {name:'K2 Algorithm'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Score-Based Structure Learning'}), (b:Concept {name:'Hill Climb Search'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'K2 Score'}), (b:Concept {name:'K2 Algorithm'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Topological Ordering'}), (b:Concept {name:'K2 Algorithm'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'K2 Score'}), (b:Concept {name:'BIC Score'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'BDeu Score'}), (b:Concept {name:'BDs Score'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Hill Climb Search'}), (b:Concept {name:'K2 Algorithm'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Structure Learning'}), (b:Concept {name:'Maximum Likelihood Estimator'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Structure Learning'}), (b:Concept {name:'Bayesian Parameter Estimation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Equivalence Class'}), (b:Concept {name:'CPDAG'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'D-Separation'}), (b:Concept {name:'Equivalence Class'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Topological Ordering'}), (b:Concept {name:'Ancestral Sampling'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Ancestral Sampling'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Ancestral Sampling'}), (b:Concept {name:'BN Simulation'}) MERGE (a)-[:PREREQ_OF]->(b);

// ── GENERALIZES_TO ────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Dynamic Bayesian Network'}), (b:Concept {name:'Hidden Markov Model'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_emission_and_transition_structure'}]->(b);
MATCH (a:Concept {name:'Hill Climb Search'}), (b:Concept {name:'K2 Algorithm'})
  MERGE (a)-[:GENERALIZES_TO {by:'unconstrained_ordering_vs_fixed_topological_ordering'}]->(b);

// ── CONTRADICTED_BY ───────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Score-Based Structure Learning'}), (b:Concept {name:'Constraint-Based Structure Learning'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Score-based may not recover all independence constraints; constraint-based is consistent but sensitive to test errors'}]->(b);
MATCH (a:Concept {name:'Equivalence Class'}), (b:Concept {name:'Domain Knowledge Constraint'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Observational data alone cannot distinguish Markov-equivalent DAGs; domain knowledge breaks the tie'}]->(b);

// ── MOTIVATES ─────────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Equivalence Class'}), (b:Concept {name:'Domain Knowledge Constraint'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Explaining Away'}), (b:Concept {name:'V-Structure'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Structure Learning'}), (b:Concept {name:'BN Simulation'})
  MERGE (a)-[:MOTIVATES]->(b);

// ── FITTED_TO ─────────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Maximum Likelihood Estimator'}), (b:Concept {name:'Bayesian Network'})
  MERGE (a)-[:FITTED_TO {method:'relative_frequency_CPD'}]->(b);
MATCH (a:Concept {name:'Bayesian Parameter Estimation'}), (b:Concept {name:'Bayesian Network'})
  MERGE (a)-[:FITTED_TO {method:'dirichlet_posterior_mean'}]->(b);
MATCH (a:Concept {name:'K2 Algorithm'}), (b:Concept {name:'Bayesian Network'})
  MERGE (a)-[:FITTED_TO {method:'greedy_score_maximization_with_ordering'}]->(b);
MATCH (a:Concept {name:'Hill Climb Search'}), (b:Concept {name:'Bayesian Network'})
  MERGE (a)-[:FITTED_TO {method:'greedy_local_search_add_remove_reverse'}]->(b);

// ── Strategy ──────────────────────────────────────────────────────────────────
MERGE (s:Strategy {name: 'Learned BN Macro Regime Signal'})
  SET s.derived_from        = 'Structure Learning',
      s.param_score         = 'K2Score',
      s.param_search        = 'HillClimbSearch',
      s.param_param_est     = 'MaximumLikelihoodEstimator',
      s.param_domain_fix    = 'manual_edge_direction_from_domain_knowledge',
      s.param_sell_threshold = 0.35,
      s.strategy_type       = 'overlay',
      s.status              = 'active',
      s.target_ticker      = 'SPY';

MATCH (s:Strategy {name:'Learned BN Macro Regime Signal'}), (c:Concept {name:'Hill Climb Search'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Learned BN Macro Regime Signal'}), (c:Concept {name:'K2 Score'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Learned BN Macro Regime Signal'}), (c:Concept {name:'Maximum Likelihood Estimator'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Macro Risk Signal'}), (c:Concept {name:'Structure Learning'}) MERGE (s)-[:DERIVED_FROM]->(c);

// ── Agent query patterns Q39–Q46 ──────────────────────────────────────────────
// Q39: Structure learning pipeline — Score-Based → Hill Climb Search → K2 Score → K2 Algorithm
// Q40: BIC/BDeu/BDs comparison — all BELONGS_TO structure_learning, select by data sparsity
// Q41: HMM regime detection — Dynamic BN → HMM → Transition Model + Emission Model
// Q42: D-separation conditional independence path — DAG → D-Separation → Markov Blanket
// Q43: Equivalence ambiguity resolution — Equivalence Class → CONTRADICTED_BY → Domain Knowledge Constraint
// Q44: Parameter learning comparison — MLE vs Bayesian Parameter Estimation → FITTED_TO Bayesian Network
// Q45: Naive Bayes signal filter — Naive Bayes Classifier → Conditional Independence → fast_signal_scoring
// Q46: Ancestral sampling validation loop — BN Simulation → Structure Learning → learned_model_check

// =============================================================================
// v0.8.0 cumulative stats:
//   Concept nodes:   251  (223 + 28)
//   Category nodes:   40  (38 + 2: structure_learning, dynamic_bayesian_networks)
//   Formula nodes:    88  (83 + 5)
//   Strategy nodes:   21  (19 + 2: Learned BN Macro Regime Signal + updated Bayesian Macro Risk Signal link)
//   Regime nodes:      7
//   Ticker nodes:     10
//   Total rel types:  17  (unchanged)
// =============================================================================

// =============================================================================
// v0.9.0 — CREDIT RISK, CLIMATE RISK & THEIR INTEGRATION
// Sources: WQU M7L1 (Climate Change as Financial Risk);
//          WQU M7L4 (7.Project.ipynb — Credit & Climate Risk in Python);
//          "Predicting Disaster with Python" (Wu et al. BN + GIS flood risk);
//          "Credit Modeling in a Deteriorating Climate" (Garnier et al. CERM);
// New concepts: 35 | New formulas: 7 | New strategies: 2
// New categories: credit_risk, climate_risk
// =============================================================================

// ── Categories ────────────────────────────────────────────────────────────────
MERGE (cat:Category {name: 'credit_risk'})
  SET cat.label = 'Credit Risk';
MERGE (cat:Category {name: 'climate_risk'})
  SET cat.label = 'Climate Risk & Sustainable Finance';

// ── Credit Risk Fundamentals ──────────────────────────────────────────────────
MERGE (c:Concept {name: 'Probability of Default'})
  SET c.definition   = 'Estimated likelihood that a borrower will fail to meet its debt obligations within a given time horizon (typically one year); denoted PD. Central parameter in expected loss calculations.',
      c.category     = 'credit_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022';

MERGE (c:Concept {name: 'Recovery Rate'})
  SET c.definition   = 'Fraction of exposure recovered after a default event; denoted RR. Typically estimated from historical seniority and collateral data. LGD = 1 − RR.',
      c.category     = 'credit_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022';

MERGE (c:Concept {name: 'Loss Given Default'})
  SET c.definition   = 'Economic loss sustained when a borrower defaults, expressed as a fraction of exposure: LGD = 1 − RR. Captures severity of loss net of recoveries.',
      c.category     = 'credit_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022';

MERGE (c:Concept {name: 'Exposure at Default'})
  SET c.definition   = 'Outstanding amount owed by a borrower at the time of default; denoted EAD. For term loans, typically the remaining principal; for revolvers, includes drawn and undrawn portions.',
      c.category     = 'credit_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022';

MERGE (c:Concept {name: 'Expected Loss'})
  SET c.definition   = 'Long-run average credit loss for a portfolio: EL = Σ PD_i × EAD_i × LGD_i. Deterministic; captures the cost of credit risk priced into loan spreads.',
      c.category     = 'credit_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022 Eq. 3–5';

MERGE (c:Concept {name: 'Unexpected Loss'})
  SET c.definition   = 'Volatility of credit losses around their expected value; the portion of credit risk requiring economic capital. UL is what VaR and ES measure beyond EL.',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022';

MERGE (c:Concept {name: 'Credit Loss Distribution'})
  SET c.definition   = 'Full probability distribution of portfolio credit losses, typically right-skewed with a heavy tail; obtained via Monte Carlo simulation or analytical models. Used to derive VaR and ES.',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4';

MERGE (c:Concept {name: 'Monte Carlo Credit Simulation'})
  SET c.definition   = 'Stochastic simulation of portfolio credit losses by drawing uniform random variables for each obligor and comparing to PD thresholds to determine defaults; aggregates EAD × LGD over defaulted loans per scenario.',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4';

MERGE (c:Concept {name: 'Vasicek Credit Model'})
  SET c.definition   = 'Single-factor Gaussian copula model for portfolio credit risk; models asset returns as X_i = √ρ·Z + √(1−ρ)·ε_i where Z is a systematic factor and ε_i is idiosyncratic. Provides an analytical formula for portfolio loss quantiles.',
      c.category     = 'credit_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L3; Vasicek 1987/2002';

MERGE (c:Concept {name: 'Merton Model'})
  SET c.definition   = 'Structural credit model treating equity as a call option on firm assets; default occurs when asset value falls below debt face value at maturity. Foundation for KMV distance-to-default and Vasicek PD formula.',
      c.category     = 'credit_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L2; Merton 1974';

MERGE (c:Concept {name: 'Three-Factor Credit Model'})
  SET c.definition   = 'Extension of the Vasicek model with three systematic risk factors (e.g., global, regional, sector) to capture correlation structure across obligors; provides finer granularity for portfolio concentration risk.',
      c.category     = 'credit_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L3';

MERGE (c:Concept {name: 'Asset Correlation'})
  SET c.definition   = 'Parameter ρ in the Vasicek model measuring the fraction of an obligor\'s asset return variance explained by the systematic factor; higher ρ implies greater co-movement and fatter portfolio loss tails.',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L3; Vasicek 2002';

MERGE (c:Concept {name: 'Distance to Default'})
  SET c.definition   = 'Number of standard deviations between a firm\'s current asset value and its default point; KMV/Merton metric. DD = (V_A − D) / (V_A · σ_A). Monotonically related to PD via the normal CDF.',
      c.category     = 'credit_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L2; Merton 1974';

MERGE (c:Concept {name: 'Credit VaR'})
  SET c.definition   = 'Value at Risk applied to the credit loss distribution; quantile loss level exceeded with probability α, typically at 99.9% confidence for regulatory capital. Credit VaR = VaR_α(L) − EL.',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4; Garnier et al. 2022';

MERGE (c:Concept {name: 'Expected Tail Loss'})
  SET c.definition   = 'Expected Shortfall applied to credit loss distribution; average loss in the worst α fraction of scenarios: ETL = E[L | L > VaR_α]. Also called Credit ES or Conditional VaR (CVaR).',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L4';

MERGE (c:Concept {name: 'Credit Portfolio Concentration'})
  SET c.definition   = 'Risk arising from unequal exposure distribution across obligors, sectors, or geographies; concentrated portfolios exhibit heavier loss tails than well-diversified ones even with identical EL.',
      c.category     = 'credit_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L3';

// ── Climate Risk Taxonomy ─────────────────────────────────────────────────────
MERGE (c:Concept {name: 'Climate Risk'})
  SET c.definition   = 'Financial risk arising from climate change; encompasses physical risk (damage from weather and warming) and transition risk (costs of moving to a low-carbon economy). Recognized by TCFD, NGFS, and Basel III frameworks.',
      c.category     = 'climate_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Feyen et al. 2020 World Bank';

MERGE (c:Concept {name: 'Physical Risk'})
  SET c.definition   = 'Climate risk arising from physical events: acute (extreme weather — floods, hurricanes, wildfires) and chronic (gradual warming, sea-level rise, drought). Directly damages assets, supply chains, and real estate collateral.',
      c.category     = 'climate_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Feyen et al. 2020';

MERGE (c:Concept {name: 'Transition Risk'})
  SET c.definition   = 'Climate risk arising from the policy, technology, and market shifts required to transition to a low-carbon economy; includes carbon pricing, stranded assets, regulatory changes, and shifts in consumer preferences.',
      c.category     = 'climate_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Feyen et al. 2020';

MERGE (c:Concept {name: 'Stranded Asset'})
  SET c.definition   = 'Asset that has suffered an unanticipated or premature write-down in value due to transition risk factors (e.g., carbon taxes making fossil fuel reserves uneconomic); key transmission channel of transition risk to financial portfolios.',
      c.category     = 'climate_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1';

MERGE (c:Concept {name: 'Climate Risk Transmission'})
  SET c.definition   = 'Channels through which climate physical and transition risks propagate to macrofinancial conditions: growth, uncertainty, financing needs, income distribution, and structural sectoral change (Feyen et al. 2020 framework).',
      c.category     = 'climate_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Feyen et al. 2020';

MERGE (c:Concept {name: 'Sustainable Finance'})
  SET c.definition   = 'Financial activity that incorporates environmental, social, and governance (ESG) considerations; directs investment capital from high-carbon to low-carbon and climate-resilient options. Umbrella term for green bonds, ESG integration, and impact investing.',
      c.category     = 'climate_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; OECD 2015';

MERGE (c:Concept {name: 'Green Bond'})
  SET c.definition   = 'Fixed-income instrument where proceeds are committed to finance or refinance green projects (renewable energy, clean transport, sustainable water management). Global issuance grew geometrically from ~$40B (2015) to >$250B (2019).',
      c.category     = 'climate_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; OECD 2015; Cheong et al. 2020';

MERGE (c:Concept {name: 'Greenwashing'})
  SET c.definition   = 'Provision of misleading information suggesting that products or investments are more environmentally sound than they actually are; key risk in sustainable finance due to lack of standardized "green" definitions.',
      c.category     = 'climate_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Foster 2022';

MERGE (c:Concept {name: 'CERM'})
  SET c.definition   = 'Climate Extended Risk Model (Garnier et al. 2022); extends the Vasicek single-factor credit model by adding a climate factor that modifies obligor PDs as a function of climate scenario severity, capturing systemic credit deterioration under warming scenarios.',
      c.category     = 'climate_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L3; Garnier et al. arXiv:2103.03275 2022';

MERGE (c:Concept {name: 'Climate-Adjusted PD'})
  SET c.definition   = 'Probability of default modified to incorporate climate scenario variables (e.g., temperature pathway, carbon price trajectory); output of CERM and similar climate credit models. Enables forward-looking credit risk assessment.',
      c.category     = 'climate_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L3; Garnier et al. 2022';

MERGE (c:Concept {name: 'BN Flood Risk Model'})
  SET c.definition   = 'Bayesian network applied to urban flood disaster risk assessment (Wu et al. 2019); integrates hydrological, socioeconomic, and infrastructure risk factors as nodes; parameterized using GIS spatial data and expert elicitation.',
      c.category     = 'climate_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Wu et al. Geomatics Nat. Hazards Risk 2019';

MERGE (c:Concept {name: 'GIS Integration'})
  SET c.definition   = 'Coupling of Geographic Information System spatial data with Bayesian network models; GIS collects and preprocesses spatial risk data (elevation, land use, drainage) that parameterizes BN nodes for localized disaster risk assessment.',
      c.category     = 'climate_risk',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Wu et al. 2019';

MERGE (c:Concept {name: 'BN Sensitivity Analysis'})
  SET c.definition   = 'Systematic perturbation of BN CPD parameters to identify which nodes most influence the target variable (e.g., flood loss); used to validate model robustness and prioritize data collection efforts.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Wu et al. 2019 pp.2166–2178';

MERGE (c:Concept {name: 'Expert Elicitation'})
  SET c.definition   = 'Structured process for encoding domain expert knowledge as prior probabilities or CPDs in a Bayesian network when empirical data are scarce; calibrated using scoring rules or comparison to historical outcomes.',
      c.category     = 'bayesian_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; Wu et al. 2019';

MERGE (c:Concept {name: 'Net Zero Commitment'})
  SET c.definition   = 'Pledge by a financial institution or corporation to reduce greenhouse gas emissions to net zero by a target date (commonly 2050); operationalized through GFANZ, NZAM, and Paris Agreement-aligned frameworks.',
      c.category     = 'climate_risk',
      c.difficulty   = 'basic',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; GFANZ 2021';

MERGE (c:Concept {name: 'Carbon Price'})
  SET c.definition   = 'Monetary cost imposed on greenhouse gas emissions (via carbon tax or cap-and-trade); key transition risk factor that makes high-carbon assets uneconomic and drives stranded asset risk.',
      c.category     = 'climate_risk',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M7L1; CERM framework';

// ── Formula nodes ─────────────────────────────────────────────────────────────
MERGE (f:Formula {id: 'f_expected_loss'})
  SET f.name       = 'Expected Loss (Credit Portfolio)',
      f.expression = 'EL = Σ_i PD_i · EAD_i · LGD_i',
      f.`latex`     = 'EL = \\sum_{i=1}^{N} PD_i \\cdot EAD_i \\cdot LGD_i',
      f.params     = ['PD_i','EAD_i','LGD_i','N'],
      f.output     = 'expected_portfolio_loss';

MERGE (f:Formula {id: 'f_lgd'})
  SET f.name       = 'Loss Given Default',
      f.expression = 'LGD = 1 - RR',
      f.`latex`     = 'LGD_i = 1 - RR_i',
      f.params     = ['RR'],
      f.output     = 'loss_given_default';

MERGE (f:Formula {id: 'f_vasicek_pd'})
  SET f.name       = 'Vasicek Conditional PD',
      f.expression = 'PD(Z) = Φ[ (Φ⁻¹(PD) - √ρ·Z) / √(1-ρ) ]',
      f.`latex`     = 'PD(Z)=\\Phi\\!\\left[\\frac{\\Phi^{-1}(PD)-\\sqrt{\\rho}\\,Z}{\\sqrt{1-\\rho}}\\right]',
      f.params     = ['PD','rho','Z'],
      f.output     = 'conditional_default_probability';

MERGE (f:Formula {id: 'f_vasicek_var'})
  SET f.name       = 'Vasicek Portfolio Loss Quantile',
      f.expression = 'q_α(L) = LGD · Φ[ (Φ⁻¹(PD) + √ρ·Φ⁻¹(α)) / √(1-ρ) ]',
      f.`latex`     = 'q_\\alpha(L)=LGD\\cdot\\Phi\\!\\left[\\frac{\\Phi^{-1}(PD)+\\sqrt{\\rho}\\,\\Phi^{-1}(\\alpha)}{\\sqrt{1-\\rho}}\\right]',
      f.params     = ['PD','rho','alpha','LGD'],
      f.output     = 'portfolio_loss_quantile';

MERGE (f:Formula {id: 'f_credit_etl'})
  SET f.name       = 'Expected Tail Loss (Credit)',
      f.expression = 'ETL_α = E[L | L > VaR_α(L)] = (1/α) · ∫_{α}^{1} q_u(L) du',
      f.`latex`     = 'ETL_\\alpha = \\frac{1}{\\alpha}\\int_\\alpha^1 q_u(L)\\,du',
      f.params     = ['alpha','loss_quantile_function'],
      f.output     = 'expected_tail_loss';

MERGE (f:Formula {id: 'f_merton_dd'})
  SET f.name       = 'Merton Distance to Default',
      f.expression = 'DD = (ln(V_A/D) + (μ - σ_A²/2)·T) / (σ_A·√T)',
      f.`latex`     = 'DD=\\frac{\\ln(V_A/D)+(\\mu-\\sigma_A^2/2)T}{\\sigma_A\\sqrt{T}}',
      f.params     = ['V_A','D','mu','sigma_A','T'],
      f.output     = 'distance_to_default';

MERGE (f:Formula {id: 'f_mc_credit_loss'})
  SET f.name       = 'Monte Carlo Credit Loss (per simulation)',
      f.expression = 'L_sim = Σ_i 1[U_i < PD_i] · LGD_i · EAD_i',
      f.`latex`     = 'L^{(s)}=\\sum_i \\mathbf{1}[U_i^{(s)}<PD_i]\\cdot LGD_i\\cdot EAD_i',
      f.params     = ['U_i','PD_i','LGD_i','EAD_i'],
      f.output     = 'simulated_portfolio_loss';

// ── BELONGS_TO ────────────────────────────────────────────────────────────────
MATCH (c:Concept {name:'Probability of Default'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Recovery Rate'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Loss Given Default'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Exposure at Default'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Expected Loss'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Unexpected Loss'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Credit Loss Distribution'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Monte Carlo Credit Simulation'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Vasicek Credit Model'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Merton Model'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Three-Factor Credit Model'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Asset Correlation'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Distance to Default'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Credit VaR'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Expected Tail Loss'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Credit Portfolio Concentration'}), (cat:Category {name:'credit_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Climate Risk'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Physical Risk'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Transition Risk'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Stranded Asset'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Climate Risk Transmission'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Sustainable Finance'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Green Bond'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Greenwashing'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'CERM'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Climate-Adjusted PD'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BN Flood Risk Model'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'GIS Integration'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Net Zero Commitment'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Carbon Price'}), (cat:Category {name:'climate_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);

// ── HAS_FORMULA ───────────────────────────────────────────────────────────────
MATCH (c:Concept {name:'Expected Loss'}), (f:Formula {id:'f_expected_loss'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Loss Given Default'}), (f:Formula {id:'f_lgd'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Vasicek Credit Model'}), (f:Formula {id:'f_vasicek_pd'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Vasicek Credit Model'}), (f:Formula {id:'f_vasicek_var'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Credit VaR'}), (f:Formula {id:'f_vasicek_var'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Expected Tail Loss'}), (f:Formula {id:'f_credit_etl'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Merton Model'}), (f:Formula {id:'f_merton_dd'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Distance to Default'}), (f:Formula {id:'f_merton_dd'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Monte Carlo Credit Simulation'}), (f:Formula {id:'f_mc_credit_loss'}) MERGE (c)-[:HAS_FORMULA]->(f);

// ── PREREQ_OF ─────────────────────────────────────────────────────────────────
// Credit chain
MATCH (a:Concept {name:'Probability of Default'}), (b:Concept {name:'Expected Loss'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Loss Given Default'}), (b:Concept {name:'Expected Loss'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Exposure at Default'}), (b:Concept {name:'Expected Loss'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Recovery Rate'}), (b:Concept {name:'Loss Given Default'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Expected Loss'}), (b:Concept {name:'Unexpected Loss'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Expected Loss'}), (b:Concept {name:'Credit Loss Distribution'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Credit Loss Distribution'}), (b:Concept {name:'Credit VaR'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Credit Loss Distribution'}), (b:Concept {name:'Expected Tail Loss'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Credit VaR'}), (b:Concept {name:'Expected Tail Loss'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Monte Carlo Credit Simulation'}), (b:Concept {name:'Credit Loss Distribution'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default'}), (b:Concept {name:'Monte Carlo Credit Simulation'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Merton Model'}), (b:Concept {name:'Vasicek Credit Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Vasicek Credit Model'}), (b:Concept {name:'Three-Factor Credit Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Asset Correlation'}), (b:Concept {name:'Vasicek Credit Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Distance to Default'}), (b:Concept {name:'Probability of Default'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Merton Model'}), (b:Concept {name:'Distance to Default'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Credit Portfolio Concentration'}), (b:Concept {name:'Credit VaR'}) MERGE (a)-[:PREREQ_OF]->(b);
// Climate chain
MATCH (a:Concept {name:'Climate Risk'}), (b:Concept {name:'Physical Risk'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Climate Risk'}), (b:Concept {name:'Transition Risk'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Transition Risk'}), (b:Concept {name:'Stranded Asset'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Carbon Price'}), (b:Concept {name:'Stranded Asset'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Climate Risk'}), (b:Concept {name:'Climate Risk Transmission'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Climate Risk'}), (b:Concept {name:'Sustainable Finance'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Sustainable Finance'}), (b:Concept {name:'Green Bond'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Green Bond'}), (b:Concept {name:'Greenwashing'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Climate Risk'}), (b:Concept {name:'Climate-Adjusted PD'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default'}), (b:Concept {name:'Climate-Adjusted PD'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Vasicek Credit Model'}), (b:Concept {name:'CERM'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Climate-Adjusted PD'}), (b:Concept {name:'CERM'}) MERGE (a)-[:PREREQ_OF]->(b);
// BN applied to climate
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'BN Flood Risk Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'BN Sensitivity Analysis'}), (b:Concept {name:'BN Flood Risk Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Expert Elicitation'}), (b:Concept {name:'BN Flood Risk Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'GIS Integration'}), (b:Concept {name:'BN Flood Risk Model'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Physical Risk'}), (b:Concept {name:'BN Flood Risk Model'}) MERGE (a)-[:PREREQ_OF]->(b);

// ── TRANSMITS_TO (climate → credit) ──────────────────────────────────────────
MATCH (a:Concept {name:'Physical Risk'}), (b:Concept {name:'Credit Loss Distribution'})
  MERGE (a)-[:TRANSMITS_TO {channel:'collateral_damage_increases_LGD_and_PD'}]->(b);
MATCH (a:Concept {name:'Transition Risk'}), (b:Concept {name:'Probability of Default'})
  MERGE (a)-[:TRANSMITS_TO {channel:'carbon_cost_erodes_earnings_raises_PD'}]->(b);
MATCH (a:Concept {name:'Climate Risk Transmission'}), (b:Concept {name:'Systemic Risk'})
  MERGE (a)-[:TRANSMITS_TO {channel:'macro_financial_spillover'}]->(b);

// ── GENERALIZES_TO ────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Vasicek Credit Model'}), (b:Concept {name:'Three-Factor Credit Model'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_regional_and_sector_systematic_factors'}]->(b);
MATCH (a:Concept {name:'Vasicek Credit Model'}), (b:Concept {name:'CERM'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_climate_scenario_factor_to_PD'}]->(b);

// ── CONTRADICTED_BY ───────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Green Bond'}), (b:Concept {name:'Greenwashing'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Lack of standardized green definitions creates label fraud risk'}]->(b);
MATCH (a:Concept {name:'Expected Loss'}), (b:Concept {name:'Credit Loss Distribution'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'EL is deterministic mean; tail risk requires full distribution via MCS or Vasicek'}]->(b);

// ── MOTIVATES ─────────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Climate Risk'}), (b:Concept {name:'CERM'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Physical Risk'}), (b:Concept {name:'BN Flood Risk Model'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Unexpected Loss'}), (b:Concept {name:'Monte Carlo Credit Simulation'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Greenwashing'}), (b:Concept {name:'Net Zero Commitment'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Transition Risk'}), (b:Concept {name:'Sustainable Finance'})
  MERGE (a)-[:MOTIVATES]->(b);

// ── Cross-links to existing concepts ─────────────────────────────────────────
// Climate risk links to systemic risk domain
MATCH (a:Concept {name:'Climate Risk Transmission'}), (b:Concept {name:'Contagion'})
  MERGE (a)-[:TRANSMITS_TO {channel:'climate_shock_propagates_through_financial_network'}]->(b);
MATCH (a:Concept {name:'Physical Risk'}), (b:Concept {name:'Stress Testing'})
  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Transition Risk'}), (b:Concept {name:'Stress Testing'})
  MERGE (a)-[:PREREQ_OF]->(b);
// Credit VaR links to VaR backtesting
MATCH (a:Concept {name:'Credit VaR'}), (b:Concept {name:'Expected Shortfall'})
  MERGE (a)-[:PREREQ_OF]->(b);
// Vasicek links to GARCH regime
MATCH (a:Concept {name:'Vasicek Credit Model'}), (b:Concept {name:'Systemic Importance Score'})
  MERGE (a)-[:PREREQ_OF]->(b);
// BN flood model links to bayesian macro
MATCH (a:Concept {name:'BN Flood Risk Model'}), (b:Concept {name:'Bayesian Macro Risk Signal'})
  MERGE (a)-[:PREREQ_OF]->(b);

// ── Strategies ────────────────────────────────────────────────────────────────
MERGE (s:Strategy {name: 'Climate Credit Risk Overlay'})
  SET s.derived_from          = 'CERM',
      s.param_model           = 'Vasicek + Climate Factor',
      s.param_pd_source       = 'Climate-Adjusted PD',
      s.param_scenarios       = ['RCP2.6','RCP4.5','RCP8.5'],
      s.param_exposure_cut    = 0.15,
      s.param_horizon_years   = 5,
      s.strategy_type         = 'overlay',
      s.status                = 'active',
      s.target_ticker      = 'XLE';

MERGE (s:Strategy {name: 'BN Physical Risk Signal'})
  SET s.derived_from          = 'BN Flood Risk Model',
      s.param_bn_library      = 'pgmpy',
      s.param_data_source     = 'GIS + Climate projections',
      s.param_sell_threshold  = 0.30,
      s.param_sectors         = ['real_estate','insurance','infrastructure'],
      s.strategy_type         = 'overlay',
      s.status                = 'active',
      s.target_ticker      = 'XLE';

MATCH (s:Strategy {name:'Climate Credit Risk Overlay'}), (c:Concept {name:'CERM'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Climate Credit Risk Overlay'}), (c:Concept {name:'Climate-Adjusted PD'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'BN Physical Risk Signal'}), (c:Concept {name:'BN Flood Risk Model'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'BN Physical Risk Signal'}), (c:Concept {name:'Physical Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);

// ── Agent query patterns Q47–Q56 ──────────────────────────────────────────────
// Q47: Full credit loss pipeline — PD + LGD + EAD → EL → MCS → Credit Loss Distribution → Credit VaR → ETL
// Q48: Vasicek loss quantile path — Asset Correlation → Vasicek Credit Model → f_vasicek_var → Credit VaR
// Q49: Merton-to-Vasicek derivation chain — Merton Model → Distance to Default → PD → Vasicek Credit Model
// Q50: Climate → Credit transmission — Physical/Transition Risk → TRANSMITS_TO → PD / LGD → CERM → Credit VaR
// Q51: BN flood risk pipeline — Physical Risk → BN Flood Risk Model → GIS Integration + Expert Elicitation
// Q52: Green finance legitimacy check — Green Bond → CONTRADICTED_BY → Greenwashing → SEC regulation signal
// Q53: Three-factor credit vs Vasicek — GENERALIZES_TO edge: Vasicek → Three-Factor; select by portfolio granularity
// Q54: Climate stress scenario — Transition Risk + Carbon Price → Stranded Asset → PD spike → Credit VaR breach
// Q55: ETL vs Credit VaR comparison — Credit VaR → Expected Tail Loss; elicitability argument from Elicitability node
// Q56: Net-zero alignment signal — Net Zero Commitment → Sustainable Finance → Green Bond → exposure_tilt

// =============================================================================
// v0.9.0 cumulative stats:
//   Concept nodes:   286  (251 + 35)
//   Category nodes:   42  (40 + 2: credit_risk, climate_risk)
//   Formula nodes:    95  (88 + 7)
//   Strategy nodes:   23  (21 + 2: Climate Credit Risk Overlay, BN Physical Risk Signal)
//   Regime nodes:      7
//   Ticker nodes:     10
//   Total rel types:  17  (unchanged; TRANSMITS_TO already existed)
// =============================================================================

// =============================================================================
// v0.10.0 — DYNAMIC BAYESIAN NETWORKS, CAUSAL STRUCTURE & BN APPLICATIONS
// Sources: WQU M8L1 (Coherent Asset Allocation & Causal Structure);
//          WQU M8L2 (Project_updated.ipynb — DYNOTEARS / VARLiNGAM);
//          "Bayesian Networks at Work: Oil Price Prediction";
//          "Estimating Probability of Default with Bayesian Networks"
// New concepts: 38 | New formulas: 4 | New strategies: 3
// New categories: causal_inference, dynamic_causal_networks, bn_applications
// =============================================================================

// ── Categories ────────────────────────────────────────────────────────────────
MERGE (cat:Category {name: 'causal_inference'})
  SET cat.label = 'Causal Inference & Econophysics';
MERGE (cat:Category {name: 'dynamic_causal_networks'})
  SET cat.label = 'Dynamic Causal Networks (DYNOTEARS/VARLiNGAM)';
MERGE (cat:Category {name: 'bn_applications'})
  SET cat.label = 'BN Applied to Finance (Credit/Commodity)';

// ── Concepts: Causal Inference & Econophysics (M8L1) ─────────────────────────
MERGE (c:Concept {name: 'Reichenbach Common Cause Principle'})
  SET c.definition   = 'If two events are correlated, then either one causes the other or a third variable (common cause) brings about the correlation; the common cause would be modeled as a parent node in a Bayesian network.',
      c.category     = 'causal_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L1; Rédei 1999; D\'Acunto et al. 2021';

MERGE (c:Concept {name: 'Common Cause'})
  SET c.definition   = 'A confounding variable that induces correlation between two observed variables without a direct causal link between them; typically encoded as a parent node in a BN shared by two child nodes.',
      c.category     = 'causal_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L1; Reichenbach 1956';

MERGE (c:Concept {name: 'Causal Structure of Equity Factors'})
  SET c.definition   = 'DAG encoding directional causal relationships among equity risk factors (value, momentum, size, quality, market); D\'Acunto et al. (2021) show the causal graph evolves over time and factor redundancy correlates with factor contagion during crises.',
      c.category     = 'causal_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|Model',
      c.source       = 'WQU M8L1; D\'Acunto et al. arXiv:2111.05072 2021';

MERGE (c:Concept {name: 'Factor Redundancy'})
  SET c.definition   = 'High causal overlap between risk factors such that one is largely explained by others in the DAG; model-selection bias generates a "zoo" of nominally new factors that are reformulations of already-exploited ones.',
      c.category     = 'causal_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'Model',
      c.source       = 'WQU M8L1; D\'Acunto et al. 2021; de Prado 2020';

MERGE (c:Concept {name: 'Knightian Uncertainty'})
  SET c.definition   = 'Frank Knight\'s distinction: risk is measurable uncertainty (known odds); Knightian uncertainty is unmeasurable (unknown odds). BN frameworks straddle both by using expert priors for uncertain events and data for risky ones.',
      c.category     = 'causal_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L1; Rebonato & Denev 2011; Knight 1921';

MERGE (c:Concept {name: 'Coherent Portfolio Optimization'})
  SET c.definition   = 'Rebonato & Denev (2011) framework: portfolio construction conditioned on the current state of the world, combining frequentist statistical analysis for normal regimes with expert-elicited BN priors for stress events. Avoids the volatility=risk conflation of mean-variance optimization.',
      c.category     = 'causal_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|Model',
      c.source       = 'WQU M8L1; Rebonato & Denev SSRN:1824207 2011';

MERGE (c:Concept {name: 'Marcenko-Pastur Distribution'})
  SET c.definition   = 'Limiting spectral distribution of eigenvalues of a large random Wishart matrix; used to distinguish noise eigenvalues (fitting MPD) from signal eigenvalues (exceeding MPD upper edge) in correlation matrix de-noising.',
      c.category     = 'causal_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M8L1; de Prado 2020 ch.2; Marcenko & Pastur 1967';

MERGE (c:Concept {name: 'Correlation Matrix De-Noising'})
  SET c.definition   = 'Removal of noise eigenvalues (those consistent with Marcenko-Pastur distribution) from the sample correlation matrix and replacement with shrunken estimates; yields a more stable inverse for portfolio optimization.',
      c.category     = 'causal_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M8L1; de Prado 2020; Moen GitHub';

MERGE (c:Concept {name: 'Correlation Matrix De-Toning'})
  SET c.definition   = 'Removal of the market factor (largest eigenvalue/eigenvector) from the de-noised correlation matrix; allows sector and idiosyncratic correlations to dominate, enabling more granular cluster detection and portfolio optimization.',
      c.category     = 'causal_inference',
      c.difficulty   = 'advanced',
      c.menu_context = 'Model',
      c.source       = 'WQU M8L1; de Prado 2020 p.31; Moen GitHub';

MERGE (c:Concept {name: 'Econophysics'})
  SET c.definition   = 'Interdisciplinary field applying methods from statistical physics (network theory, random matrix theory, spin models) to financial and economic systems; underpins Marcenko-Pastur correlation de-noising and contagion cascade models.',
      c.category     = 'causal_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr|Model',
      c.source       = 'WQU M8L1';

MERGE (c:Concept {name: 'Quant Meltdown 2007'})
  SET c.definition   = 'August 2007 event when factor-invested equity portfolios simultaneously unwound, causing rapid contagion across long-short strategies; demonstrated that leverage combined with factor redundancy transforms ostensibly low-risk strategies into high-risk ones.',
      c.category     = 'causal_inference',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L1; D\'Acunto et al. 2021';

// ── Concepts: Dynamic Causal Networks (M8L2 notebook) ────────────────────────
MERGE (c:Concept {name: 'DYNOTEARS'})
  SET c.definition   = 'Structure learning algorithm for dynamic Bayesian networks from time-series data (Pamfil et al. 2020); simultaneously learns intra-slice (contemporaneous) and inter-slice (lagged) causal edges using a continuous acyclicity constraint; scales to hundreds of nodes.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'WQU M8L2; Pamfil et al. arXiv:2002.00498 2020';

MERGE (c:Concept {name: 'VARLiNGAM'})
  SET c.definition   = 'Vector Autoregression + Linear Non-Gaussian Acyclic Model; modern replacement for DYNOTEARS in the lingam library; learns both contemporaneous (intra-slice) and lagged (inter-slice) causal structure from time series under non-Gaussianity assumptions.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'WQU M8L2 Project_updated.ipynb; lingam library';

MERGE (c:Concept {name: 'Intra-Slice Matrix'})
  SET c.definition   = 'Adjacency matrix B encoding contemporaneous (same time-step) causal effects between variables in a dynamic BN; B[i,j] ≠ 0 means variable j causally influences variable i within the same time period.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2; Pamfil et al. 2020';

MERGE (c:Concept {name: 'Inter-Slice Matrix'})
  SET c.definition   = 'Adjacency matrix A encoding lagged causal effects between time steps in a dynamic BN; A[i,j] ≠ 0 means variable j at time t−1 causally influences variable i at time t.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2; Pamfil et al. 2020';

MERGE (c:Concept {name: 'Causal Edge Threshold'})
  SET c.definition   = 'Minimum absolute weight below which causal edges are pruned from the learned dynamic BN graph; controls sparsity and noise suppression. Chosen to balance graph interpretability against false-negative edge removal.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2';

MERGE (c:Concept {name: 'Complex Contagion'})
  SET c.definition   = 'Contagion model where spreading requires exposure to multiple infected neighbors (threshold model), contrasting with simple contagion where a single contact suffices; describes financial crisis propagation that requires correlated exposures.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2; Centola & Macy 2007';

MERGE (c:Concept {name: 'Cascade Effect'})
  SET c.definition   = 'Sequential chain of failures triggered by an initial shock; each failure increases the probability of subsequent failures. In dynamic BN: a high-weight inter-slice path AIG_lag1 → AIG → BofA → WFC → JPM → C observed in 2008 crisis data.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2; Pamfil et al. 2020';

MERGE (c:Concept {name: 'Causal Intervention'})
  SET c.definition   = 'do-calculus operation that simulates the effect of externally forcing a variable to a value (severing incoming edges in the causal DAG) to estimate causal effects rather than mere associations; Pearl\'s intervention vs observation distinction.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2; Pearl 2000';

MERGE (c:Concept {name: 'Epidemic Model'})
  SET c.definition   = 'SIR/SIS-type spreading model applied to financial contagion; nodes transition between susceptible, infected (distressed), and recovered states; threshold determines whether contagion goes systemic.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2';

MERGE (c:Concept {name: 'Largest Connected Subgraph'})
  SET c.definition   = 'The maximal weakly connected component of a causal graph; used to isolate the most interconnected cluster of assets in DYNOTEARS/VARLiNGAM analysis, filtering out unconnected noise stocks.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2';

MERGE (c:Concept {name: 'Standardized Log Return'})
  SET c.definition   = 'Log return normalized to zero mean and unit variance: r* = (log(P_t/P_{t-1}) − μ) / σ; standard preprocessing for DYNOTEARS/VARLiNGAM to ensure scale-invariant causal weight estimation.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'basic',
      c.menu_context = 'Model',
      c.source       = 'WQU M8L2; Pamfil et al. 2020';

MERGE (c:Concept {name: 'Sector Causal Clustering'})
  SET c.definition   = 'Empirical observation that intra-slice causal weights are strongest within sectors (financials, healthcare, tech) relative to across sectors; confirmed by VARLiNGAM on S&P 100 (2014–2019) heatmap.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'WQU M8L2; Pamfil et al. 2020 Fig.4';

// ── Concepts: BN for Oil Price Prediction ────────────────────────────────────
MERGE (c:Concept {name: 'Oil Price BN'})
  SET c.definition   = 'Bayesian network modeling oil price dynamics as a function of supply factors (OPEC production, spare capacity), demand factors (global GDP growth, China demand), geopolitical risk, and inventory levels; used for probabilistic price forecasting.',
      c.category     = 'bn_applications',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|Model',
      c.source       = 'BN at Work: Oil Price Prediction';

MERGE (c:Concept {name: 'Geopolitical Risk Factor'})
  SET c.definition   = 'BN node encoding the probability of supply-disrupting geopolitical events (sanctions, conflict, embargo); key driver of oil price tail risk; quantified via GPR index (Caldara & Iacoviello 2022) or expert elicitation.',
      c.category     = 'bn_applications',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'BN at Work: Oil Price Prediction';

MERGE (c:Concept {name: 'OPEC Supply Factor'})
  SET c.definition   = 'BN node representing OPEC production decisions and compliance; interacts with spare capacity and geopolitical risk to determine oil supply levels; encoded as a discrete CPD with states (increase, maintain, cut).',
      c.category     = 'bn_applications',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'BN at Work: Oil Price Prediction';

MERGE (c:Concept {name: 'Commodity Price Factor BN'})
  SET c.definition   = 'General BN architecture for commodity price modeling; nodes span macro demand drivers, supply constraints, inventory, currency effects, and geopolitical risk; enables probabilistic scenario analysis beyond point forecasts.',
      c.category     = 'bn_applications',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr|Model',
      c.source       = 'BN at Work: Oil Price Prediction';

// ── Concepts: BN for PD Estimation ───────────────────────────────────────────
MERGE (c:Concept {name: 'BN Credit Scoring'})
  SET c.definition   = 'Bayesian network used to estimate probability of default by modeling the causal relationships between financial ratios (leverage, liquidity, profitability, coverage) and default outcome; allows Bayesian updating as new accounting data arrives.',
      c.category     = 'bn_applications',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Estimating PD with Bayesian Networks';

MERGE (c:Concept {name: 'Financial Ratio Node'})
  SET c.definition   = 'BN node representing a discretized financial ratio (e.g., debt-to-equity, current ratio, return-on-assets); CPDs encode empirical distributions conditional on parent nodes (sector, rating, macro regime).',
      c.category     = 'bn_applications',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Estimating PD with Bayesian Networks';

MERGE (c:Concept {name: 'Bayesian Credit Scorecard'})
  SET c.definition   = 'Credit scoring model where posterior PD is updated via Bayes theorem as new obligor-specific information (financial statements, payment history) arrives; replaces static logistic regression scores with dynamic Bayesian updates.',
      c.category     = 'bn_applications',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Estimating PD with Bayesian Networks';

MERGE (c:Concept {name: 'Rating Migration BN'})
  SET c.definition   = 'Bayesian network encoding transition probabilities between credit rating states (AAA→AA, BB→B, etc.); extends static transition matrices by conditioning migrations on macro variables (GDP growth, credit spread regime).',
      c.category     = 'bn_applications',
      c.difficulty   = 'advanced',
      c.menu_context = 'RiskMgr',
      c.source       = 'Estimating PD with Bayesian Networks';

MERGE (c:Concept {name: 'Bayesian PD Update'})
  SET c.definition   = 'Application of Bayes theorem to revise an obligor\'s PD estimate as new evidence arrives: P(Default | new_data) ∝ P(new_data | Default) · P(Default). Enables real-time credit risk monitoring.',
      c.category     = 'bn_applications',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Estimating PD with Bayesian Networks; WQU M8L3';

MERGE (c:Concept {name: 'BN vs Logistic Regression'})
  SET c.definition   = 'Comparison of BN and logistic regression for PD estimation; BN allows explicit encoding of causal structure and handles missing data via marginalization; logistic regression is faster but treats predictors as independent and cannot propagate uncertainty through a causal chain.',
      c.category     = 'bn_applications',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr|MLModel',
      c.source       = 'Estimating PD with Bayesian Networks';

MERGE (c:Concept {name: 'Macro Regime Conditioning'})
  SET c.definition   = 'Incorporating the current macroeconomic regime (expansion, contraction, stress) as a conditioning variable in credit and portfolio BNs; enables state-dependent PD, LGD, and asset correlation estimates beyond through-the-cycle averages.',
      c.category     = 'bn_applications',
      c.difficulty   = 'intermediate',
      c.menu_context = 'RiskMgr',
      c.source       = 'Estimating PD with Bayesian Networks; Coherent Asset Allocation';

MERGE (c:Concept {name: 'CausalNex'})
  SET c.definition   = 'Discontinued Python library (QuantumBlack/McKinsey) for DYNOTEARS-based dynamic BN structure learning; replaced by lingam (VARLiNGAM) and networkx for graph visualization in updated implementations.',
      c.category     = 'dynamic_causal_networks',
      c.difficulty   = 'basic',
      c.menu_context = 'MLModel',
      c.source       = 'WQU M8L2 Project_updated.ipynb';

// ── Formula nodes ─────────────────────────────────────────────────────────────
MERGE (f:Formula {id: 'f_marcenko_pastur'})
  SET f.name       = 'Marcenko-Pastur Upper Edge',
      f.expression = 'λ_max = σ² · (1 + √(T/N))²  ;  λ_min = σ² · (1 − √(T/N))²',
      f.`latex`     = '\\lambda_{\\max/\\min}=\\sigma^2\\!\\left(1\\pm\\sqrt{T/N}\\right)^2',
      f.params     = ['sigma_sq','T','N'],
      f.output     = 'eigenvalue_noise_boundary';

MERGE (f:Formula {id: 'f_standardized_log_return'})
  SET f.name       = 'Standardized Log Return',
      f.expression = 'r*_t = (log(P_t / P_{t-1}) − μ) / σ',
      f.`latex`     = 'r^*_t = \\frac{\\ln(P_t/P_{t-1})-\\mu}{\\sigma}',
      f.params     = ['P_t','P_{t-1}','mu','sigma'],
      f.output     = 'standardized_return';

MERGE (f:Formula {id: 'f_var1_dynamic_bn'})
  SET f.name       = 'VAR(1) Dynamic BN Structural Equation',
      f.expression = 'X_t = B · X_t + A · X_{t-1} + ε_t',
      f.`latex`     = '\\mathbf{X}_t = B\\mathbf{X}_t + A\\mathbf{X}_{t-1} + \\boldsymbol{\\varepsilon}_t',
      f.params     = ['B_intra','A_lag','X_t','epsilon_t'],
      f.output     = 'causal_time_series_decomposition';

MERGE (f:Formula {id: 'f_bayesian_pd_update'})
  SET f.name       = 'Bayesian PD Posterior Update',
      f.expression = 'P(D=1 | X=x) = P(X=x | D=1) · P(D=1) / P(X=x)',
      f.`latex`     = 'P(D\\!=\\!1|\\mathbf{X}\\!=\\!\\mathbf{x})=\\frac{P(\\mathbf{X}\\!=\\!\\mathbf{x}|D\\!=\\!1)\\,P(D\\!=\\!1)}{P(\\mathbf{X}\\!=\\!\\mathbf{x})}',
      f.params     = ['prior_PD','likelihood_X_given_D','evidence_X'],
      f.output     = 'posterior_probability_of_default';
// ── BELONGS_TO ────────────────────────────────────────────────────────────────
MATCH (c:Concept {name:'Reichenbach Common Cause Principle'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Common Cause'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Causal Structure of Equity Factors'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Factor Redundancy'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Knightian Uncertainty'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Coherent Portfolio Optimization'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Marcenko-Pastur Distribution'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Correlation Matrix De-Noising'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Correlation Matrix De-Toning'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Econophysics'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Quant Meltdown 2007'}), (cat:Category {name:'causal_inference'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'DYNOTEARS'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'VARLiNGAM'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Intra-Slice Matrix'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Inter-Slice Matrix'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Causal Edge Threshold'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Complex Contagion'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Cascade Effect'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Causal Intervention'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Epidemic Model'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Largest Connected Subgraph'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Standardized Log Return'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Sector Causal Clustering'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'CausalNex'}), (cat:Category {name:'dynamic_causal_networks'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Oil Price BN'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Geopolitical Risk Factor'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'OPEC Supply Factor'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Commodity Price Factor BN'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BN Credit Scoring'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Financial Ratio Node'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Bayesian Credit Scorecard'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Rating Migration BN'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Bayesian PD Update'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'BN vs Logistic Regression'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name:'Macro Regime Conditioning'}), (cat:Category {name:'bn_applications'}) MERGE (c)-[:BELONGS_TO]->(cat);

// ── HAS_FORMULA ───────────────────────────────────────────────────────────────
MATCH (c:Concept {name:'Marcenko-Pastur Distribution'}), (f:Formula {id:'f_marcenko_pastur'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Correlation Matrix De-Noising'}), (f:Formula {id:'f_marcenko_pastur'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Standardized Log Return'}), (f:Formula {id:'f_standardized_log_return'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'DYNOTEARS'}), (f:Formula {id:'f_var1_dynamic_bn'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'VARLiNGAM'}), (f:Formula {id:'f_var1_dynamic_bn'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Intra-Slice Matrix'}), (f:Formula {id:'f_var1_dynamic_bn'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Bayesian PD Update'}), (f:Formula {id:'f_bayesian_pd_update'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (c:Concept {name:'Bayesian Credit Scorecard'}), (f:Formula {id:'f_bayesian_pd_update'}) MERGE (c)-[:HAS_FORMULA]->(f);

// ── PREREQ_OF ─────────────────────────────────────────────────────────────────
// Causal inference chain
MATCH (a:Concept {name:'Reichenbach Common Cause Principle'}), (b:Concept {name:'Common Cause'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Common Cause'}), (b:Concept {name:'Causal Structure of Equity Factors'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Conditional Independence'}), (b:Concept {name:'Reichenbach Common Cause Principle'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Coherent Portfolio Optimization'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Knightian Uncertainty'}), (b:Concept {name:'Coherent Portfolio Optimization'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Expert Elicitation'}), (b:Concept {name:'Coherent Portfolio Optimization'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Marcenko-Pastur Distribution'}), (b:Concept {name:'Correlation Matrix De-Noising'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Correlation Matrix De-Noising'}), (b:Concept {name:'Correlation Matrix De-Toning'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Factor Redundancy'}), (b:Concept {name:'Quant Meltdown 2007'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Causal Structure of Equity Factors'}), (b:Concept {name:'Factor Redundancy'}) MERGE (a)-[:PREREQ_OF]->(b);
// Dynamic causal network chain
MATCH (a:Concept {name:'Dynamic Bayesian Network'}), (b:Concept {name:'DYNOTEARS'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Structure Learning'}), (b:Concept {name:'DYNOTEARS'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DYNOTEARS'}), (b:Concept {name:'VARLiNGAM'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DYNOTEARS'}), (b:Concept {name:'Intra-Slice Matrix'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DYNOTEARS'}), (b:Concept {name:'Inter-Slice Matrix'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'VARLiNGAM'}), (b:Concept {name:'Intra-Slice Matrix'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'VARLiNGAM'}), (b:Concept {name:'Inter-Slice Matrix'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Intra-Slice Matrix'}), (b:Concept {name:'Sector Causal Clustering'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Causal Edge Threshold'}), (b:Concept {name:'Largest Connected Subgraph'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Standardized Log Return'}), (b:Concept {name:'VARLiNGAM'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Contagion'}), (b:Concept {name:'Complex Contagion'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Complex Contagion'}), (b:Concept {name:'Cascade Effect'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'DAG'}), (b:Concept {name:'Causal Intervention'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'D-Separation'}), (b:Concept {name:'Causal Intervention'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Cascade Effect'}), (b:Concept {name:'Epidemic Model'}) MERGE (a)-[:PREREQ_OF]->(b);
// BN applications chain
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'Oil Price BN'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Geopolitical Risk Factor'}), (b:Concept {name:'Oil Price BN'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'OPEC Supply Factor'}), (b:Concept {name:'Oil Price BN'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Oil Price BN'}), (b:Concept {name:'Commodity Price Factor BN'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Network'}), (b:Concept {name:'BN Credit Scoring'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default'}), (b:Concept {name:'BN Credit Scoring'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Financial Ratio Node'}), (b:Concept {name:'BN Credit Scoring'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'BN Credit Scoring'}), (b:Concept {name:'Bayesian Credit Scorecard'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian Credit Scorecard'}), (b:Concept {name:'Bayesian PD Update'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Probability of Default'}), (b:Concept {name:'Rating Migration BN'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Bayesian PD Update'}), (b:Concept {name:'Climate-Adjusted PD'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Macro Regime Conditioning'}), (b:Concept {name:'BN Credit Scoring'}) MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Macro Regime Conditioning'}), (b:Concept {name:'Coherent Portfolio Optimization'}) MERGE (a)-[:PREREQ_OF]->(b);

// ── GENERALIZES_TO ────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'DYNOTEARS'}), (b:Concept {name:'VARLiNGAM'})
  MERGE (a)-[:GENERALIZES_TO {by:'relaxing_Gaussianity_to_non-Gaussian_innovations'}]->(b);
MATCH (a:Concept {name:'BN Credit Scoring'}), (b:Concept {name:'Bayesian Credit Scorecard'})
  MERGE (a)-[:GENERALIZES_TO {by:'adding_sequential_Bayesian_updating_of_CPDs'}]->(b);
MATCH (a:Concept {name:'Correlation Matrix De-Noising'}), (b:Concept {name:'Correlation Matrix De-Toning'})
  MERGE (a)-[:GENERALIZES_TO {by:'additionally_removing_market_eigenvalue'}]->(b);
MATCH (a:Concept {name:'Epidemic Model'}), (b:Concept {name:'Complex Contagion'})
  MERGE (a)-[:GENERALIZES_TO {by:'threshold_exposure_requirement_vs_single_contact'}]->(b);

// ── CONTRADICTED_BY ───────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Coherent Portfolio Optimization'}), (b:Concept {name:'Knightian Uncertainty'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'MVO equates volatility with risk and ignores deep uncertainty; Rebonato-Denev framework explicitly models unknown unknowns via BN priors'}]->(b);
MATCH (a:Concept {name:'BN Credit Scoring'}), (b:Concept {name:'BN vs Logistic Regression'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Logistic regression ignores causal structure and cannot propagate uncertainty; BN trades computational speed for causal transparency'}]->(b);
MATCH (a:Concept {name:'Factor Redundancy'}), (b:Concept {name:'Causal Structure of Equity Factors'})
  MERGE (a)-[:CONTRADICTED_BY {reason:'Static factor models mask causal overlap; dynamic causal graph reveals which factors are truly independent vs redundant through time'}]->(b);

// ── MOTIVATES ─────────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Factor Redundancy'}), (b:Concept {name:'Coherent Portfolio Optimization'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Quant Meltdown 2007'}), (b:Concept {name:'Causal Structure of Equity Factors'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Knightian Uncertainty'}), (b:Concept {name:'Expert Elicitation'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Cascade Effect'}), (b:Concept {name:'DYNOTEARS'})
  MERGE (a)-[:MOTIVATES]->(b);
MATCH (a:Concept {name:'Geopolitical Risk Factor'}), (b:Concept {name:'Oil Price BN'})
  MERGE (a)-[:MOTIVATES]->(b);

// ── TRANSMITS_TO ──────────────────────────────────────────────────────────────
MATCH (a:Concept {name:'Factor Redundancy'}), (b:Concept {name:'Contagion'})
  MERGE (a)-[:TRANSMITS_TO {channel:'leverage_amplifies_factor_overlap_into_fire_sale'}]->(b);
MATCH (a:Concept {name:'Cascade Effect'}), (b:Concept {name:'Systemic Risk'})
  MERGE (a)-[:TRANSMITS_TO {channel:'inter-institution_causal_chain_amplifies_initial_shock'}]->(b);

// ── Cross-domain linkages ─────────────────────────────────────────────────────
MATCH (a:Concept {name:'DYNOTEARS'}), (b:Concept {name:'Systemic Risk Measurement'})
  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'VARLiNGAM'}), (b:Concept {name:'Financial Network'})
  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Sector Causal Clustering'}), (b:Concept {name:'Network Centrality'})
  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Rating Migration BN'}), (b:Concept {name:'Probability of Default'})
  MERGE (a)-[:PREREQ_OF]->(b);
MATCH (a:Concept {name:'Coherent Portfolio Optimization'}), (b:Concept {name:'Bayesian Network'})
  MERGE (a)-[:PREREQ_OF]->(b);

// ── Strategies ────────────────────────────────────────────────────────────────
MERGE (s:Strategy {name: 'DYNOTEARS Contagion Signal'})
  SET s.derived_from       = 'DYNOTEARS',
      s.param_library      = 'lingam VARLiNGAM',
      s.param_lags         = 1,
      s.param_criterion    = 'bic',
      s.param_threshold    = 0.25,
      s.param_window       = '2008-09-01 to 2008-11-30',
      s.param_universe     = 'SP100_Financials',
      s.strategy_type      = 'systemic_risk_signal',
      s.status             = 'active',
      s.target_ticker      = 'XLF';

MERGE (s:Strategy {name: 'BN Oil Price Signal'})
  SET s.derived_from       = 'Oil Price BN',
      s.param_nodes        = ['OPEC_Supply','Geopolitical_Risk','Global_Demand','Inventory','Oil_Price'],
      s.param_sell_threshold = 0.40,
      s.param_buy_threshold  = 0.35,
      s.strategy_type      = 'commodity_overlay',
      s.status             = 'active',
      s.target_ticker      = 'XLE';

MERGE (s:Strategy {name: 'Bayesian Credit Signal'})
  SET s.derived_from          = 'BN Credit Scoring',
      s.param_model           = 'BN + Bayesian PD Update',
      s.param_ratio_nodes     = ['Leverage','Liquidity','Profitability','Coverage'],
      s.param_pd_threshold    = 0.05,
      s.param_macro_conditioning = true,
      s.strategy_type         = 'credit_overlay',
      s.status                = 'active',
      s.target_ticker      = 'XLF';

MATCH (s:Strategy {name:'DYNOTEARS Contagion Signal'}), (c:Concept {name:'DYNOTEARS'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'DYNOTEARS Contagion Signal'}), (c:Concept {name:'VARLiNGAM'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'DYNOTEARS Contagion Signal'}), (c:Concept {name:'Cascade Effect'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'BN Oil Price Signal'}), (c:Concept {name:'Oil Price BN'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'BN Oil Price Signal'}), (c:Concept {name:'Geopolitical Risk Factor'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Credit Signal'}), (c:Concept {name:'BN Credit Scoring'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name:'Bayesian Credit Signal'}), (c:Concept {name:'Bayesian PD Update'}) MERGE (s)-[:DERIVED_FROM]->(c);

// ── Agent query patterns Q57–Q68 ──────────────────────────────────────────────
// Q57: DYNOTEARS pipeline — Structure Learning → DYNOTEARS → Intra-Slice + Inter-Slice → Causal Edge Threshold → Largest Subgraph
// Q58: AIG 2008 cascade path — AIG_lag1 → AIG → BofA/WFC/JPM/C via Inter-Slice → Intra-Slice causal chain
// Q59: Common Cause detection — Reichenbach → Common Cause → parent node BN → D-Separation test
// Q60: Factor redundancy to contagion path — Factor Redundancy → TRANSMITS_TO → Contagion → Systemic Risk
// Q61: Coherent portfolio construction — Knightian Uncertainty + Expert Elicitation + BN → Coherent Portfolio Optimization
// Q62: De-noise/de-tone path — Marcenko-Pastur → De-Noising → De-Toning → stable correlation matrix for optimizer
// Q63: Oil price scenario — Geopolitical Risk + OPEC Supply → Oil Price BN → commodity exposure hedge signal
// Q64: Credit BN vs logistic — BN Credit Scoring → CONTRADICTED_BY → BN vs Logistic Regression → decision by interpretability need
// Q65: Bayesian PD monitoring — Financial Ratio Node → BN Credit Scoring → Bayesian PD Update → real-time credit monitoring
// Q66: Rating migration conditioned on macro — Macro Regime Conditioning → Rating Migration BN → PD vector update
// Q67: Sector clustering signal — VARLiNGAM → Sector Causal Clustering → network centrality → concentration risk
// Q68: Causal intervention stress test — Causal Intervention (do-calculus) → shock node → cascade propagation path

// =============================================================================
// v0.10.0 cumulative stats:
//   Concept nodes:   324  (286 + 38)
//   Category nodes:   45  (42 + 3: causal_inference, dynamic_causal_networks, bn_applications)
//   Formula nodes:    99  (95 + 4)
//   Strategy nodes:   26  (23 + 3: DYNOTEARS Contagion Signal, BN Oil Price Signal, Bayesian Credit Signal)
//   Regime nodes:      7
//   Ticker nodes:     10
//   Total rel types:  17  (unchanged)
// =============================================================================

// =============================================================================
// v0.10.1 — ASSESSMENT Q&A BANK (WQU Risk Management M6–M8)
// 51 QuizQuestion nodes | new node type | new rel type: TESTS
// Sources: Cooper & Herskovits, Schreiber, Coscia, pgmpy, Wu et al., Wouters,
//          quantpi, Garnier et al., Spolaor, Alvi, Carraro, D'Acunto, Rebonato,
//          Pamfil et al., Dablander & Hinne
// =============================================================================

// ── Module 6: BN Structure & Parameter Learning ───────────────────────────────
MERGE (q:QuizQuestion {id:'Q-M6-1'})
  SET q.question   = 'Which two challenges does K2 address with fundamentally the same technique?',
      q.correct    = 'Missing data and hidden variables',
      q.distractors= ['Time complexity and noisy data','Hidden variables and time complexity','Missing data and noisy data'],
      q.source     = 'Cooper & Herskovits 1992',
      q.module     = 'M6', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M6-2'})
  SET q.question   = 'When comparing network posterior probabilities, Cooper & Herskovits do which?',
      q.correct    = 'Calculate the ratios of the networks joint probabilities with the data',
      q.distractors= ['Approximate ratios assuming equal priors','Calculate posteriors adjusting for priors','Approximate posteriors assuming equal priors'],
      q.source     = 'Cooper & Herskovits 1992',
      q.module     = 'M6', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M6-3'})
  SET q.question   = 'Under certain conditions (all alpha=1), the Dirichlet distribution reduces to which?',
      q.correct    = 'Uniform distribution',
      q.distractors= ['Gamma distribution','Beta distribution','Binomial distribution'],
      q.source     = 'Cooper & Herskovits 1992',
      q.module     = 'M6', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M6-4'})
  SET q.question   = 'What is the key feature of a Bayesian network according to Cooper & Herskovits?',
      q.correct    = 'Its explicit representation of the conditional independence and dependence among events',
      q.distractors= ['Its ability to represent any event probability','Its requirement for explicit prior probability assumptions','Its explicit representation of hypothetical dependency relationships'],
      q.source     = 'Cooper & Herskovits 1992',
      q.module     = 'M6', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M6-5'})
  SET q.question   = 'Iterating over all triplets to identify conditional independencies specifying edge presence and direction is a method of which?',
      q.correct    = 'Constraint learning',
      q.distractors= ['Search and score','Approximate algorithms','Forward learning'],
      q.source     = 'Schreiber',
      q.module     = 'M6', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M6-6'})
  SET q.question   = 'The Chow-Liu tree calculates which quantity between all variable pairs before finding the maximum spanning tree?',
      q.correct    = 'Mutual information',
      q.distractors= ['Relative entropy','Granger causality','Joint entropy'],
      q.source     = 'Schreiber',
      q.module     = 'M6', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M6-7'})
  SET q.question   = 'Typical BN objective functions do which?',
      q.correct    = 'Balance the log probability of the data given the model with the complexity of the model',
      q.distractors= ['Minimize number of model parameters','Minimize log probability of data given model','Maximize log probability of data given model'],
      q.source     = 'Schreiber',
      q.module     = 'M6', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M6-8'})
  SET q.question   = 'Which is true about cycles according to Coscia?',
      q.correct    = 'A cycle is a path that begins and ends with the same node',
      q.distractors= ['A directed graph cannot have a cycle','All undirected networks have cycles','A cycle is a walk that begins and ends with the same node'],
      q.source     = 'Coscia',
      q.module     = 'M6', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M6-9'})
  SET q.question   = 'What is the most common global information about a network connectivity according to Coscia?',
      q.correct    = 'The average degree',
      q.distractors= ['The number of nodes divided by two','The sum of degrees','The number of nodes'],
      q.source     = 'Coscia',
      q.module     = 'M6', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M6-10'})
  SET q.question   = 'Which describes most networks from a degree distribution according to Coscia?',
      q.correct    = 'There are many orders of magnitude between the minimum and the maximum degree',
      q.distractors= ['Many orders of magnitude between most and least popular degree value','Degrees have roughly normal distribution on log-log scale','Degrees have roughly normal distribution on linear scale'],
      q.source     = 'Coscia',
      q.module     = 'M6', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M6-11'})
  SET q.question   = 'Which are true about connected components? (multi-select)',
      q.correct    = 'If two nodes cannot be connected by a path they are on different components; If two nodes cannot be connected by a walk they are on different components; Connected components are subgraphs whose nodes can be reached following edges',
      q.distractors= ['Real-world networks tend not to have multiple components'],
      q.source     = 'Coscia',
      q.module     = 'M6', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M6-12'})
  SET q.question   = 'In pgmpy, how do we add both marginal and conditional probability distributions?',
      q.correct    = 'With the general method add_cpds for both',
      q.distractors= ['With get_cpds','With add_cpds and add_pds','With add_pds for both'],
      q.source     = 'pgmpy M6L4',
      q.module     = 'M6', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M6-13'})
  SET q.question   = 'What must be done to display Conditional Probability Tables in pgmpy?',
      q.correct    = 'Convert the CPD object to a DataFrame',
      q.distractors= ['Convert the DataFrame to a CPD object','Convert the DataFrame to a Pandas object','Convert the DataFrame to a NumPy object'],
      q.source     = 'pgmpy M6L4',
      q.module     = 'M6', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M6-14'})
  SET q.question   = 'Which methods were used to learn the network structure in M6L4?',
      q.correct    = 'HillClimbSearch and K2Score',
      q.distractors= ['K2Score and MaximumLikelihoodEstimator','HillClimbSearch and MaximumLikelihoodEstimator','MaximumLikelihoodEstimator and K2_best_model'],
      q.source     = 'pgmpy M6L4',
      q.module     = 'M6', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M6-15'})
  SET q.question   = 'Setting X[:,3]=X[:,1] and X[:,6]=X[:,1] in Schreiber code accomplishes what?',
      q.correct    = 'Establishes variables 3 and 6 as children of variable 1',
      q.distractors= ['Creates connections between variables 1 3 and 6','Establishes 3 and 6 as parents of 1','Creates connections 1-3 and 1-6 but not 3-6'],
      q.source     = 'Schreiber',
      q.module     = 'M6', q.difficulty = 'intermediate';

// ── Module 7: Credit & Climate Risk ──────────────────────────────────────────
MERGE (q:QuizQuestion {id:'Q-M7-1'})
  SET q.question   = 'Wu et al. describe "the number of people and impacted infrastructure" as which?',
      q.correct    = 'Disaster bearer',
      q.distractors= ['Disaster driver','Disaster environment','Decision variable'],
      q.source     = 'Wu et al. 2019',
      q.module     = 'M7', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M7-2'})
  SET q.question   = 'Wu et al. define "conditions and surroundings where flood damage occurred" as which?',
      q.correct    = 'Disaster environment',
      q.distractors= ['Disaster driver','Disaster bearer','Decision variable'],
      q.source     = 'Wu et al. 2019',
      q.module     = 'M7', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M7-3'})
  SET q.question   = 'Which does Wouters consider physical risk drivers? (multi-select)',
      q.correct    = 'Flooding; Drought',
      q.distractors= ['Sustainability rating (label)','Policy'],
      q.source     = 'Wouters',
      q.module     = 'M7', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M7-4'})
  SET q.question   = 'Which are true according to Wouters? (multi-select)',
      q.correct    = 'Energy label can impact LTV; Physical risk can negatively impact LTV; Energy label can impact PD',
      q.distractors= ['Transition risk can decrease the EAD'],
      q.source     = 'Wouters',
      q.module     = 'M7', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M7-5'})
  SET q.question   = 'According to quantpi, which is generally true about PD?',
      q.correct    = 'It varies over time',
      q.distractors= ['It is static','It decreases over time','It increases over time'],
      q.source     = 'quantpi',
      q.module     = 'M7', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M7-6'})
  SET q.question   = 'According to quantpi, how is the Vasicek threshold defined?',
      q.correct    = 'The inverse normal of the unconditional probability of default',
      q.distractors= ['The normal CDF of the conditional PD','The normal CDF of the unconditional PD','The inverse normal of the conditional PD'],
      q.source     = 'quantpi',
      q.module     = 'M7', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M7-7'})
  SET q.question   = 'In Vasicek with very many borrowers, conditional PD is only conditional on which?',
      q.correct    = 'General economic conditions',
      q.distractors= ['Correlation among borrowers','Loss given default','Idiosyncratic borrower conditions'],
      q.source     = 'quantpi',
      q.module     = 'M7', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M7-8'})
  SET q.question   = 'According to quantpi, what is the loss rate l(S)?',
      q.correct    = 'Loss amount / exposure',
      q.distractors= ['Loss amount x LGD / exposure','LGD / exposure','LGD x exposure'],
      q.source     = 'quantpi',
      q.module     = 'M7', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M7-9'})
  SET q.question   = 'Garnier et al. recommend how many samples to estimate the 1-alpha quantile without variance reduction?',
      q.correct    = 'N = 100 / alpha',
      q.distractors= ['N = 100 x alpha','N = 10 x alpha','N = 10000 / alpha'],
      q.source     = 'Garnier et al. 2022',
      q.module     = 'M7', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M7-10'})
  SET q.question   = 'In CERM, a group can represent which? (multi-select)',
      q.correct    = 'A geographic region; An economic sector; A rating level',
      q.distractors= ['A climate risk mitigation and adaptation strategy'],
      q.source     = 'Garnier et al. 2022',
      q.module     = 'M7', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M7-11'})
  SET q.question   = 'Per BIS definition, if capital for a loan depends only on that loans characteristics, the model is?',
      q.correct    = 'Portfolio invariant',
      q.distractors= ['Institution specific','Uncorrelated','Merton model'],
      q.source     = 'BIS / Vasicek',
      q.module     = 'M7', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M7-12'})
  SET q.question   = 'With small sample sizes, which approximate inference performs well according to Spolaor?',
      q.correct    = 'Only MCMC (Gibbs) performs well initially',
      q.distractors= ['All three perform well','All three perform well with large samples','With large samples only Gibbs performs well'],
      q.source     = 'Spolaor',
      q.module     = 'M7', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M7-13'})
  SET q.question   = 'Which are closely associated with Approximate Inference? (multi-select)',
      q.correct    = 'MCMC method; Gibbs sampling; Weighted sampling',
      q.distractors= ['Variable elimination'],
      q.source     = 'Spolaor',
      q.module     = 'M7', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M7-14'})
  SET q.question   = 'Which are usually expressed as a percentage? (multi-select)',
      q.correct    = 'Probability of default; Loss given default',
      q.distractors= ['Exposure at default','Expected loss'],
      q.source     = 'WQU M7L4',
      q.module     = 'M7', q.difficulty = 'basic';

// ── Module 8: Dynamic BNs, Causal Structure, Applications ─────────────────────
MERGE (q:QuizQuestion {id:'Q-M8-1'})
  SET q.question   = 'According to Alvi, for what is the hmms Python library used?',
      q.correct    = 'To identify bull and bear regimes in time-series data',
      q.distractors= ['To retrieve data as dataframes','To train the network','To clean data'],
      q.source     = 'Alvi',
      q.module     = 'M8', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M8-2'})
  SET q.question   = 'According to Alvi, what are transitions between hidden states assumed to be?',
      q.correct    = 'A first-order Markov chain',
      q.distractors= ['A Markov chain of any order greater than one','A second-order Markov chain','A zero-order Markov chain'],
      q.source     = 'Alvi',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-3'})
  SET q.question   = 'According to Alvi, which Python library provides fast flexible and expressive data structures?',
      q.correct    = 'pandas',
      q.distractors= ['hmms','numpy','pgmpy'],
      q.source     = 'Alvi',
      q.module     = 'M8', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M8-4'})
  SET q.question   = 'Match Alvis four regime detection stages to descriptions.',
      q.correct    = 'Stage1: Transform TS to emission sequence; Stage2: Learn model parameters (Baum-Welch); Stage3: Find most likely hidden states (Viterbi); Stage4: Identify latent meaning of each hidden state',
      q.distractors= ['Constructing oil market structure (not a stage)','Capturing causal relationships (not a stage)'],
      q.source     = 'Alvi',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-5'})
  SET q.question   = 'Which macroeconomic variable is NOT used by Carraro?',
      q.correct    = 'Population growth',
      q.distractors= ['Inflation rate','Gross domestic product','Unemployment'],
      q.source     = 'Carraro',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-6'})
  SET q.question   = 'According to Carraro, which variable has highest arc frequency to the PD node?',
      q.correct    = 'Non-performing Loans (NPL)',
      q.distractors= ['Return on Risk-adjusted Capital (RORAC)','Inflation','Unemployment'],
      q.source     = 'Carraro',
      q.module     = 'M8', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M8-7'})
  SET q.question   = 'According to Carraro, which are true about BN graph terminology? (multi-select)',
      q.correct    = 'Parents are a subset of ancestors; Children are a subset of descendants',
      q.distractors= ['Children are a subset of parents','Ancestors are a subset of parents'],
      q.source     = 'Carraro',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-8'})
  SET q.question   = 'According to D\'Acunto et al., which is known as the fear index?',
      q.correct    = 'VIX',
      q.distractors= ['CBOE','Yield spread','f-z score'],
      q.source     = 'D\'Acunto et al. 2021',
      q.module     = 'M8', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M8-9'})
  SET q.question   = 'According to D\'Acunto et al., which is NOT one of the three families of causal structure learning?',
      q.correct    = 'Silhouette statistics',
      q.distractors= ['Constraint-based approaches','Score-based methods','Structural causal models'],
      q.source     = 'D\'Acunto et al. 2021',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-10'})
  SET q.question   = 'According to Rebonato, which does the econophysics school believe? (multi-select)',
      q.correct    = 'Exceptional financial events exhibit persistent regularities; The tail behavior of return distributions is stable',
      q.distractors= ['Tail behavior should be forecast case-by-case','The Bayesian approach is better than frequentist'],
      q.source     = 'Rebonato',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-11'})
  SET q.question   = 'According to Rebonato and Denev, the Markowitz approach does which?',
      q.correct    = 'Turns a complex problem of utility maximization under constraints into a simple optimization of the variance-return trade-off',
      q.distractors= ['Turns complex variance-return into simple utility maximization','Turns simple variance-return into complex utility maximization','Turns simple utility maximization into complex variance-return'],
      q.source     = 'Rebonato & Denev 2011',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-12'})
  SET q.question   = 'According to Pamfil et al., dynamic BNs are known in econometrics as which?',
      q.correct    = 'Structural Vector Autoregressive (SVAR) models',
      q.distractors= ['ARCH models','Black-box optimizations','Second-order optimization schemes'],
      q.source     = 'Pamfil et al. 2020',
      q.module     = 'M8', q.difficulty = 'advanced';

MERGE (q:QuizQuestion {id:'Q-M8-13'})
  SET q.question   = 'According to Pamfil et al., what occurs when intra-slice weights are ordered by sector?',
      q.correct    = 'An approximately block-diagonal structure emerges',
      q.distractors= ['An X-shaped double-diagonal structure emerges','Dispersion of weights is almost perfectly random','Dispersion is concentrated in the center'],
      q.source     = 'Pamfil et al. 2020',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-14'})
  SET q.question   = 'According to Coscia, which is a model to describe the dynamics of disease?',
      q.correct    = 'Compartmental',
      q.distractors= ['Homogeneous mixing','Super spreader','Peer-to-peer'],
      q.source     = 'Coscia',
      q.module     = 'M8', q.difficulty = 'basic';

MERGE (q:QuizQuestion {id:'Q-M8-15'})
  SET q.question   = 'According to Coscia, outbreak growth in power-law networks with large hubs is described as?',
      q.correct    = 'Super-exponential',
      q.distractors= ['Hypergeometric','Geometric','Logarithmic'],
      q.source     = 'Coscia',
      q.module     = 'M8', q.difficulty = 'intermediate';

MERGE (q:QuizQuestion {id:'Q-M8-16'})
  SET q.question   = 'Which are true about the Z→X Z→Y causal graph? (multi-select)',
      q.correct    = 'Z is the parent of X and Y; X and Y are descendants of Z',
      q.distractors= ['X and Y are spouses','X and Y are neighbors of Z'],
      q.source     = 'Dablander & Hinne 2019; Carraro',
      q.module     = 'M8', q.difficulty = 'intermediate';

// ── TESTS relationships (QuizQuestion → Concept) ──────────────────────────────
MATCH (q:QuizQuestion {id:'Q-M6-1'}), (c:Concept {name:'K2 Algorithm'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-2'}), (c:Concept {name:'K2 Score'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-3'}), (c:Concept {name:'Bayesian Parameter Estimation'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-4'}), (c:Concept {name:'Bayesian Network'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-5'}), (c:Concept {name:'Constraint-Based Structure Learning'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-6'}), (c:Concept {name:'Structure Learning'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-7'}), (c:Concept {name:'BIC Score'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-8'}), (c:Concept {name:'DAG'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-9'}), (c:Concept {name:'Financial Network'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-10'}), (c:Concept {name:'Network Centrality'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-11'}), (c:Concept {name:'Largest Connected Subgraph'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-12'}), (c:Concept {name:'Bayesian Network'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-13'}), (c:Concept {name:'Bayesian Network'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-14'}), (c:Concept {name:'Hill Climb Search'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-14'}), (c:Concept {name:'K2 Score'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M6-15'}), (c:Concept {name:'Common Cause'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-1'}), (c:Concept {name:'BN Flood Risk Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-2'}), (c:Concept {name:'BN Flood Risk Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-3'}), (c:Concept {name:'Physical Risk'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-4'}), (c:Concept {name:'Transition Risk'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-4'}), (c:Concept {name:'Exposure at Default'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-5'}), (c:Concept {name:'Probability of Default'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-6'}), (c:Concept {name:'Vasicek Credit Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-7'}), (c:Concept {name:'Vasicek Credit Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-8'}), (c:Concept {name:'Credit Loss Distribution'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-9'}), (c:Concept {name:'Monte Carlo Credit Simulation'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-10'}), (c:Concept {name:'CERM'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-11'}), (c:Concept {name:'Vasicek Credit Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-12'}), (c:Concept {name:'Gibbs Sampling'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-13'}), (c:Concept {name:'Importance Sampling'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-14'}), (c:Concept {name:'Probability of Default'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M7-14'}), (c:Concept {name:'Loss Given Default'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-1'}), (c:Concept {name:'Hidden Markov Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-2'}), (c:Concept {name:'Transition Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-3'}), (c:Concept {name:'Dynamic Bayesian Network'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-4'}), (c:Concept {name:'Hidden Markov Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-5'}), (c:Concept {name:'Macro Regime Conditioning'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-6'}), (c:Concept {name:'BN Credit Scoring'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-7'}), (c:Concept {name:'Bayesian Network'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-8'}), (c:Concept {name:'Causal Structure of Equity Factors'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-9'}), (c:Concept {name:'Score-Based Structure Learning'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-9'}), (c:Concept {name:'Constraint-Based Structure Learning'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-10'}), (c:Concept {name:'Econophysics'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-11'}), (c:Concept {name:'Coherent Portfolio Optimization'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-12'}), (c:Concept {name:'DYNOTEARS'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-13'}), (c:Concept {name:'Sector Causal Clustering'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-14'}), (c:Concept {name:'Epidemic Model'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-15'}), (c:Concept {name:'Complex Contagion'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-16'}), (c:Concept {name:'Common Cause'}) MERGE (q)-[:TESTS]->(c);
MATCH (q:QuizQuestion {id:'Q-M8-16'}), (c:Concept {name:'Reichenbach Common Cause Principle'}) MERGE (q)-[:TESTS]->(c);

// =============================================================================
// v0.10.1 cumulative stats:
//   QuizQuestion nodes:  51  (new node type)
//   TESTS relationships: 54  (new rel type)
//   All other node/edge counts unchanged from v0.10.0
// =============================================================================

// =============================================================================
// 25. NEUTRAL-REGIME ACTIVATION (calm-market strategies) — Alpaca submission
//     Neutral fires these active, ticker-mapped strategies so the live paper loop
//     still trades (and demos) in calm markets where the regime threshold sit at Neutral.
// =============================================================================
MATCH (s:Strategy {name:'Multi-Factor Long-Short'}), (r:Regime {name:'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);
MATCH (s:Strategy {name:'Smart Beta Tilt'}),          (r:Regime {name:'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.50}]->(r);
MATCH (s:Strategy {name:'Momentum Breakout'}),        (r:Regime {name:'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.45}]->(r);
// =============================================================================
// 26. STRATEGY SIGNAL-METHOD + TRADEABILITY (Alpaca submission) — idempotent
//     Adds the dispatch contract (signal_method) and marks options/derivatives
//     heritage strategies inactive so the live Alpaca equity/ETF paper loop only
//     trades what it can actually execute.
// =============================================================================
MERGE (s:Strategy {name: 'Momentum Breakout'})
  SET s.signal_method = 'momentum', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Volatility Mean Reversion'})
  SET s.signal_method = 'vol_zscore', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Factor Momentum Rotation'})
  SET s.signal_method = 'momentum', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Multi-Factor Long-Short'})
  SET s.signal_method = 'momentum', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Smart Beta Tilt'})
  SET s.signal_method = 'value_mr', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Systemic Risk Hedge'})
  SET s.signal_method = 'crisis_hedge', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Contagion Path Avoidance'})
  SET s.signal_method = 'contagion', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'DYNOTEARS Contagion Signal'})
  SET s.signal_method = 'contagion', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Bayesian Macro Risk Signal'})
  SET s.signal_method = 'bn_macro', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Bayesian Credit Signal'})
  SET s.signal_method = 'value_mr', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'Climate Credit Risk Overlay'})
  SET s.signal_method = 'climate', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'BN Physical Risk Signal'})
  SET s.signal_method = 'climate', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
MERGE (s:Strategy {name: 'BN Oil Price Signal'})
  SET s.signal_method = 'momentum', s.tradeable_venue = 'alpaca_equity', s.status = 'active';
// ── Mark options/derivatives/VaR/monitor heritage strategies INACTIVE for the
//    Alpaca equity/ETF paper universe (kept research_only so KG Q&A still works)
MERGE (s:Strategy {name: 'Delta-Neutral Carry'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Gamma Scalp'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Vol Surface Arb'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Long Variance Swap'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Short Variance Swap (Vol Premium Harvest)'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Jump-Filtered Vol Trading'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Transformer Vol Forecast'})
  SET s.signal_method = 'vol_trading', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'GARCH-EVT VaR Overlay'})
  SET s.signal_method = 'garch_vol', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Asymmetric Vol Regime Signal'})
  SET s.signal_method = 'garch_vol', s.tradeable_venue = 'options_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Learned BN Macro Regime Signal'})
  SET s.signal_method = 'bn_macro', s.tradeable_venue = 'research_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'DeepVaR Risk Overlay'})
  SET s.signal_method = 'risk', s.tradeable_venue = 'research_only', s.status = 'inactive';
MERGE (s:Strategy {name: 'Granger Contagion Monitor'})
  SET s.signal_method = 'contagion', s.tradeable_venue = 'research_only', s.status = 'inactive';

// ===== OPTION STRATEGY LIBRARY (Alpaca options paper trading) =====
MERGE (s:Strategy {name: 'Covered Call Income'})
  SET s.signal_method = 'covered_call', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Sell OTM call against a long underlying for theta income; REF: Time Decay (Theta), Delta Hedging.',
      s.param_budget_pct = 0.1, s.param_delta_lo = 0.16, s.param_delta_hi = 0.28,
      s.param_dte_lo = 30, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Covered Call Income'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.85}]->(r);
MATCH (s:Strategy {name: 'Covered Call Income'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.7}]->(r);
MATCH (s:Strategy {name: 'Covered Call Income'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Covered Call Income'}), (c:Concept {name: 'Time Decay (Theta)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Covered Call Income'}), (c:Concept {name: 'Delta Hedging'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Cash-Secured Put'})
  SET s.signal_method = 'cash_secured_put', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Sell OTM put backed by cash collateral at a support strike; mean-reversion premium harvest.',
      s.param_budget_pct = 0.12, s.param_delta_lo = 0.15, s.param_delta_hi = 0.25,
      s.param_dte_lo = 30, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Cash-Secured Put'}), (r:Regime {name: 'MeanReverting'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.85}]->(r);
MATCH (s:Strategy {name: 'Cash-Secured Put'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Cash-Secured Put'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Cash-Secured Put'}), (c:Concept {name: 'Variance Risk Premium'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Bull Call Debit Spread'})
  SET s.signal_method = 'call_debit_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Buy ATM call, sell higher-strike call; bullish defined-risk direction.',
      s.param_budget_pct = 0.08, s.param_delta_lo = 0.28, s.param_delta_hi = 0.4,
      s.param_dte_lo = 21, s.param_dte_hi = 60;

MATCH (s:Strategy {name: 'Bull Call Debit Spread'}), (r:Regime {name: 'Trending'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.75}]->(r);
MATCH (s:Strategy {name: 'Bull Call Debit Spread'}), (r:Regime {name: 'Recovery'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.65}]->(r);
MATCH (s:Strategy {name: 'Bull Call Debit Spread'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Bull Call Debit Spread'}), (c:Concept {name: 'Delta Hedging'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Bear Put Debit Spread'})
  SET s.signal_method = 'put_debit_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Buy ATM put, sell lower-strike put; bearish defined-risk direction.',
      s.param_budget_pct = 0.08, s.param_delta_lo = 0.28, s.param_delta_hi = 0.4,
      s.param_dte_lo = 21, s.param_dte_hi = 60;

MATCH (s:Strategy {name: 'Bear Put Debit Spread'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.75}]->(r);
MATCH (s:Strategy {name: 'Bear Put Debit Spread'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Bear Put Debit Spread'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Put Credit Spread'})
  SET s.signal_method = 'put_credit_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Sell OTM put, buy further-OTM put; credit collection with defined loss.',
      s.param_budget_pct = 0.08, s.param_delta_lo = 0.15, s.param_delta_hi = 0.25,
      s.param_dte_lo = 30, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Put Credit Spread'}), (r:Regime {name: 'MeanReverting'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.7}]->(r);
MATCH (s:Strategy {name: 'Put Credit Spread'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Put Credit Spread'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.55}]->(r);
MATCH (s:Strategy {name: 'Put Credit Spread'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Put Credit Spread'}), (c:Concept {name: 'Variance Risk Premium'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Iron Condor'})
  SET s.signal_method = 'iron_condor', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Sell OTM call+put wings; range-bound defined-risk credit.',
      s.param_budget_pct = 0.08, s.param_delta_lo = 0.15, s.param_delta_hi = 0.25,
      s.param_dte_lo = 30, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Iron Condor'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.85}]->(r);
MATCH (s:Strategy {name: 'Iron Condor'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.65}]->(r);
MATCH (s:Strategy {name: 'Iron Condor'}), (c:Concept {name: 'Put-Call Parity'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Calendar Spread'})
  SET s.signal_method = 'calendar_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Sell near-dated ATM, buy far-dated; vega+theta differential.',
      s.param_budget_pct = 0.06, s.param_delta_lo = 0.35, s.param_delta_hi = 0.45,
      s.param_dte_lo = 21, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Calendar Spread'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.7}]->(r);
MATCH (s:Strategy {name: 'Calendar Spread'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.55}]->(r);
MATCH (s:Strategy {name: 'Calendar Spread'}), (c:Concept {name: 'Time Decay (Theta)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Calendar Spread'}), (c:Concept {name: 'Vega Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Diagonal Spread'})
  SET s.signal_method = 'diagonal_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Buy far-dated, sell near-dated OTM; directional theta harvest.',
      s.param_budget_pct = 0.06, s.param_delta_lo = 0.25, s.param_delta_hi = 0.4,
      s.param_dte_lo = 21, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Diagonal Spread'}), (r:Regime {name: 'Trending'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Diagonal Spread'}), (r:Regime {name: 'Recovery'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.55}]->(r);
MATCH (s:Strategy {name: 'Diagonal Spread'}), (c:Concept {name: 'Time Decay (Theta)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Collar'})
  SET s.signal_method = 'collar', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Long stock + long protective put + short OTM call; capped hedge for a fee.',
      s.param_budget_pct = 0.1, s.param_delta_lo = 0.12, s.param_delta_hi = 0.2,
      s.param_dte_lo = 30, s.param_dte_hi = 60;

MATCH (s:Strategy {name: 'Collar'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.55}]->(r);
MATCH (s:Strategy {name: 'Collar'}), (r:Regime {name: 'Recovery'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.5}]->(r);
MATCH (s:Strategy {name: 'Collar'}), (c:Concept {name: 'Delta Hedging'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Collar'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Protective Put'})
  SET s.signal_method = 'protective_put', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Long put against long underlying; crisis insurance (corr->1).',
      s.param_budget_pct = 0.08, s.param_delta_lo = 0.15, s.param_delta_hi = 0.25,
      s.param_dte_lo = 21, s.param_dte_hi = 45;

MATCH (s:Strategy {name: 'Protective Put'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Protective Put'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.85}]->(r);
MATCH (s:Strategy {name: 'Protective Put'}), (r:Regime {name: 'SystemicStress'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.9}]->(r);
MATCH (s:Strategy {name: 'Protective Put'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Protective Put'}), (c:Concept {name: 'Delta Hedging'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Long Straddle'})
  SET s.signal_method = 'long_straddle', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Buy ATM call+put; long-vol, event-driven directional.',
      s.param_budget_pct = 0.05, s.param_delta_lo = 0.45, s.param_delta_hi = 0.55,
      s.param_dte_lo = 7, s.param_dte_hi = 21;

MATCH (s:Strategy {name: 'Long Straddle'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.65}]->(r);
MATCH (s:Strategy {name: 'Long Straddle'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Long Straddle'}), (c:Concept {name: 'Vega Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Long Straddle'}), (c:Concept {name: 'Gamma Scalping'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Short Straddle'})
  SET s.signal_method = 'short_straddle', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Sell ATM call+put; short-vol range income under tight risk.',
      s.param_budget_pct = 0.05, s.param_delta_lo = 0.45, s.param_delta_hi = 0.55,
      s.param_dte_lo = 14, s.param_dte_hi = 30;

MATCH (s:Strategy {name: 'Short Straddle'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.75}]->(r);
MATCH (s:Strategy {name: 'Short Straddle'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.55}]->(r);
MATCH (s:Strategy {name: 'Short Straddle'}), (c:Concept {name: 'Vega Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Short Straddle'}), (c:Concept {name: 'Variance Risk Premium'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Long Strangle'})
  SET s.signal_method = 'long_strangle', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Buy OTM call+put; cheap long-vol tail.',
      s.param_budget_pct = 0.04, s.param_delta_lo = 0.2, s.param_delta_hi = 0.3,
      s.param_dte_lo = 7, s.param_dte_hi = 21;

MATCH (s:Strategy {name: 'Long Strangle'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.62}]->(r);
MATCH (s:Strategy {name: 'Long Strangle'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.58}]->(r);
MATCH (s:Strategy {name: 'Long Strangle'}), (c:Concept {name: 'Vega Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MERGE (s:Strategy {name: 'Put-Spread Crash Hedge'})
  SET s.signal_method = 'put_spread_hedge', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Buy OTM put, sell deeper-OTM put; pre-funded crash insurance.',
      s.param_budget_pct = 0.06, s.param_delta_lo = 0.08, s.param_delta_hi = 0.15,
      s.param_dte_lo = 30, s.param_dte_hi = 60;

MATCH (s:Strategy {name: 'Put-Spread Crash Hedge'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.9}]->(r);
MATCH (s:Strategy {name: 'Put-Spread Crash Hedge'}), (r:Regime {name: 'SystemicStress'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.95}]->(r);
MATCH (s:Strategy {name: 'Put-Spread Crash Hedge'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight: 0.6}]->(r);
MATCH (s:Strategy {name: 'Put-Spread Crash Hedge'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Put-Spread Crash Hedge'}), (c:Concept {name: 'Variance Risk Premium'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Put-Spread Crash Hedge'}), (c:Concept {name: 'Delta Hedging'}) MERGE (s)-[:DERIVED_FROM]->(c);

// Contradiction edges (opposite vol / direction views)
MATCH (a:Strategy {name: 'Iron Condor'}), (b:Strategy {name: 'Long Straddle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Iron Condor'}), (b:Strategy {name: 'Short Straddle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Short Straddle'}), (b:Strategy {name: 'Long Straddle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Short Straddle'}), (b:Strategy {name: 'Long Strangle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Put Credit Spread'}), (b:Strategy {name: 'Put-Spread Crash Hedge'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Bull Call Debit Spread'}), (b:Strategy {name: 'Put-Spread Crash Hedge'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Covered Call Income'}), (b:Strategy {name: 'Protective Put'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Cash-Secured Put'}), (b:Strategy {name: 'Bull Call Debit Spread'}) MERGE (a)-[:CONTRADICTED_BY]->(b);


// ===== HULL CH.11 EXPANSION (Butterfly/Strip/Strap/Strangle/Bear-Call/Box) =====
MERGE (c:Concept {name: 'Early Assignment Risk'})
  SET c.description = 'Hull Ch11 BS11.1: American options can be exercised early; \"risk-free\" multi-leg constructs (e.g. box spreads) are not risk-free on American single-stock options.',
      c.difficulty = 'advanced';

MERGE (s:Strategy {name: 'Long Butterfly'})
  SET s.signal_method = 'butterfly', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Hull 11.3: buy K1+K3 wings, sell 2x ATM K2; profits if price pins near K2, small max loss elsewhere.',
      s.param_budget_pct = 0.05, s.param_delta_lo = 0.45, s.param_delta_hi = 0.55,
      s.param_dte_lo = 14, s.param_dte_hi = 45;
MATCH (s:Strategy {name: 'Long Butterfly'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name: 'Long Butterfly'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.65}]->(r);
MATCH (s:Strategy {name: 'Long Butterfly'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Long Butterfly'}), (c:Concept {name: 'Gamma Scalping'}) MERGE (s)-[:DERIVED_FROM]->(c);

MERGE (s:Strategy {name: 'Short Butterfly'})
  SET s.signal_method = 'short_butterfly', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Hull 11.3: sell K1/K3 wings, buy 2x ATM K2; profits on a significant move either way, small loss on stillness.',
      s.param_budget_pct = 0.05, s.param_delta_lo = 0.45, s.param_delta_hi = 0.55,
      s.param_dte_lo = 14, s.param_dte_hi = 45;
MATCH (s:Strategy {name: 'Short Butterfly'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name: 'Short Butterfly'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);
MATCH (s:Strategy {name: 'Short Butterfly'}), (c:Concept {name: 'Vega Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Short Butterfly'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);

MERGE (s:Strategy {name: 'Strip'})
  SET s.signal_method = 'strip', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Hull 11.4: 1 ATM call + 2 ATM puts; bearish-tilted big-move bet.',
      s.param_budget_pct = 0.05, s.param_delta_lo = 0.45, s.param_delta_hi = 0.55,
      s.param_dte_lo = 7, s.param_dte_hi = 30;
MATCH (s:Strategy {name: 'Strip'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.65}]->(r);
MATCH (s:Strategy {name: 'Strip'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'Strip'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Strip'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);

MERGE (s:Strategy {name: 'Strap'})
  SET s.signal_method = 'strap', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Hull 11.4: 2 ATM calls + 1 ATM put; bullish-tilted big-move bet.',
      s.param_budget_pct = 0.05, s.param_delta_lo = 0.45, s.param_delta_hi = 0.55,
      s.param_dte_lo = 7, s.param_dte_hi = 30;
MATCH (s:Strategy {name: 'Strap'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'Strap'}), (r:Regime {name: 'Trending'}) MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);
MATCH (s:Strategy {name: 'Strap'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Strap'}), (c:Concept {name: 'European Put Option'}) MERGE (s)-[:DERIVED_FROM]->(c);

MERGE (s:Strategy {name: 'Short Strangle'})
  SET s.signal_method = 'short_strangle', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Hull 11.4: sell OTM call + sell OTM put; range-bound income, widest break-evens - top vertical combination.',
      s.param_budget_pct = 0.06, s.param_delta_lo = 0.15, s.param_delta_hi = 0.25,
      s.param_dte_lo = 21, s.param_dte_hi = 45;
MATCH (s:Strategy {name: 'Short Strangle'}), (r:Regime {name: 'LowVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.8}]->(r);
MATCH (s:Strategy {name: 'Short Strangle'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'Short Strangle'}), (c:Concept {name: 'Vega Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Short Strangle'}), (c:Concept {name: 'Time Decay (Theta)'}) MERGE (s)-[:DERIVED_FROM]->(c);

MERGE (s:Strategy {name: 'Bear Call Credit Spread'})
  SET s.signal_method = 'call_credit_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'active', s.description = 'Hull 11.1/11.2: sell lower-strike call, buy higher-strike call; bearish credit spread (defined risk).',
      s.param_budget_pct = 0.08, s.param_delta_lo = 0.2, s.param_delta_hi = 0.3,
      s.param_dte_lo = 21, s.param_dte_hi = 60;
MATCH (s:Strategy {name: 'Bear Call Credit Spread'}), (r:Regime {name: 'MeanReverting'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'Bear Call Credit Spread'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.55}]->(r);
MATCH (s:Strategy {name: 'Bear Call Credit Spread'}), (c:Concept {name: 'European Call Option'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Bear Call Credit Spread'}), (c:Concept {name: 'Time Decay (Theta)'}) MERGE (s)-[:DERIVED_FROM]->(c);

MERGE (s:Strategy {name: 'Box Spread'})
  SET s.signal_method = 'box_spread', s.strategy_type = 'option', s.tradeable_venue = 'alpaca_options',
      s.status = 'research_only', s.description = 'Hull 11.3 BS11.1: bull call + bear put at same strikes = theoretically risk-free on European, BUT American early-exercise makes it NOT risk-free - research only, never auto-traded.',
      s.param_budget_pct = 0.0;
MATCH (s:Strategy {name: 'Box Spread'}), (c:Concept {name: 'Early Assignment Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Covered Call Income'}), (c:Concept {name: 'Early Assignment Risk'}) MERGE (s)-[:DERIVED_FROM]->(c);

// Contradictions: opposing vol/direction books
MATCH (a:Strategy {name: 'Short Strangle'}), (b:Strategy {name: 'Long Straddle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Long Butterfly'}), (b:Strategy {name: 'Short Butterfly'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Strip'}), (b:Strategy {name: 'Short Strangle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Strap'}), (b:Strategy {name: 'Short Strangle'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Bear Call Credit Spread'}), (b:Strategy {name: 'Bull Call Debit Spread'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
// =============================================================================

// ===============================================================================

// ===============================================================================
// REFERENCE BOOKS TO KNOWLEDGE GRAPH (Hybrid GraphRAG source) - schema 0.4.0
// ===============================================================================
MERGE (:Book {id: 'aat-2017', title: 'Advanced Algorithmic Trading', author: 'Halls-Moore & Tatman', source: 'REF/aat-2017.md'});
MERGE (:Book {id: 'hull-8ed', title: 'Options, Futures and Other Derivatives', author: 'John C. Hull', source: 'REF/hull-8ed.md'});
MERGE (:Book {id: 'tradmarkets', title: 'Traditional Financial Markets', author: 'WorldQuant University M2', source: 'REF/tradmarkets.md'});
MERGE (:Book {id: 'alternativeinstruments', title: 'Alternative Financial Markets', author: 'WorldQuant University M2', source: 'REF/alternativeinstruments.md'});
MERGE (:Book {id: 'credit_risk', title: 'Credit Risk and Financing', author: 'WorldQuant University M8', source: 'REF/credit_risk.md'});
MERGE (:Book {id: 'liquidity_regulation', title: 'Liquidity and Regulation', author: 'WorldQuant University M10', source: 'REF/liquidity_regulation.md'});
MERGE (:Book {id: 'model_failure', title: 'Model Failure and Crises', author: 'WorldQuant University M11', source: 'REF/model_failure.md'});
MERGE (:Book {id: 'volatility_correlation', title: 'Volatility and Correlation', author: 'WorldQuant University M9', source: 'REF/volatility_correlation.md'});
MERGE (:Book {id: 'module5', title: 'Module 5: Nonlinearity, Leverage, Mean Reversion', author: 'WorldQuant University M5', source: 'REF/module5.md'});
MERGE (:Book {id: 'buildingagents', title: 'Building AI Agents with LLMs, RAG, and KGs', author: 'Arseneau et al.', source: 'REF/buildingagents.md'});
MERGE (:Category {name: 'bayesian_statistics', display: 'Bayesian Statistics'});
MERGE (:Category {name: 'time_series_analysis', display: 'Time Series Analysis'});
MERGE (:Category {name: 'machine_learning_trading', display: 'Machine Learning Trading'});
MERGE (:Category {name: 'qstrader_strategies', display: 'Qstrader Strategies'});
MERGE (:Category {name: 'market_microstructure', display: 'Market Microstructure'});
MERGE (:Category {name: 'liquidity_regulation', display: 'Liquidity Regulation'});
MERGE (:Category {name: 'model_risk', display: 'Model Risk'});
MERGE (:Category {name: 'credit_financing', display: 'Credit Financing'});
MERGE (:Category {name: 'volatility_correlation', display: 'Volatility Correlation'});
MERGE (:Category {name: 'derivatives_markets', display: 'Derivatives Markets'});
MERGE (:Category {name: 'rag_systems', display: 'Rag Systems'});
MERGE (:Category {name: 'agents_orchestration', display: 'Agents Orchestration'});
MERGE (:Concept {name: 'Bayes\' Rule', definition: 'Posterior = likelihood x prior / evidence. Core of Bayesian inference.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Bayes\' Rule'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Bayes\' Rule'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Bayes\' Rule'}), (b:Concept {name: 'Prior Distribution'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'Bayes\' Rule'}), (b:Concept {name: 'Likelihood Function'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'Bayes\' Rule'}), (b:Concept {name: 'Posterior Distribution'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Prior Distribution', definition: 'Initial belief about a parameter before observing data.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Prior Distribution'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Prior Distribution'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Likelihood Function', definition: 'Probability of observing the data given a parameter value.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Likelihood Function'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Likelihood Function'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Posterior Distribution', definition: 'Updated belief after conditioning on observed data via Bayes\' rule.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Posterior Distribution'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Posterior Distribution'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Posterior Distribution'}), (b:Concept {name: 'Bayes\' Rule'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Conjugate Prior', definition: 'Prior that yields a posterior in the same family; beta-binomial is the canonical example.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Conjugate Prior'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Conjugate Prior'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Conjugate Prior'}), (b:Concept {name: 'Posterior Distribution'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Beta-Binomial Model', definition: 'Beta prior + binomial likelihood gives closed-form posterior; used for Bernoulli success probabilities.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Beta-Binomial Model'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Beta-Binomial Model'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Beta-Binomial Model'}), (b:Concept {name: 'Conjugate Prior'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Markov Chain Monte Carlo', definition: 'Sample from complex posteriors by constructing a Markov chain with the posterior as stationary distribution.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Markov Chain Monte Carlo'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Markov Chain Monte Carlo'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Markov Chain Monte Carlo'}), (b:Concept {name: 'Posterior Distribution'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Metropolis-Hastings', definition: 'MCMC sampler using proposal + accept/reject rule; converges to target posterior.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Metropolis-Hastings'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Metropolis-Hastings'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Metropolis-Hastings'}), (b:Concept {name: 'Markov Chain Monte Carlo'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'NUTS Sampler', definition: 'No-U-Turn Sampler; efficient Hamiltonian MCMC variant (PyMC3 default).', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'NUTS Sampler'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'NUTS Sampler'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'NUTS Sampler'}), (b:Concept {name: 'Metropolis-Hastings'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Bayesian Linear Regression', definition: 'Linear regression with Gaussian priors on coefficients; posterior predictive distribution.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Bayesian Linear Regression'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Bayesian Linear Regression'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Bayesian Linear Regression'}), (b:Concept {name: 'Bayes\' Rule'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Bayesian Stochastic Volatility', definition: 'Treat volatility as a latent variable; posterior over vol regimes via MCMC.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Bayesian Stochastic Volatility'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Bayesian Stochastic Volatility'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Bayesian Stochastic Volatility'}), (b:Concept {name: 'Markov Chain Monte Carlo'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Bayesian Credible Interval', definition: 'Interval covering a given posterior probability mass; Bayesian analog of confidence interval.', category: 'bayesian_statistics', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Bayesian Credible Interval'}), (cat:Category {name: 'bayesian_statistics'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Bayesian Credible Interval'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Bayesian Credible Interval'}), (b:Concept {name: 'Posterior Distribution'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Stationarity', definition: 'A series is stationary if its joint distribution is invariant to time shift (constant mean/var/ACF).', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Stationarity'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Stationarity'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'White Noise', definition: 'Zero-mean i.i.d. process; the building block of ARMA models.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'White Noise'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'White Noise'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'White Noise'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Random Walk', definition: 'Non-stationary series whose increments are white noise; unit-root process.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Random Walk'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Random Walk'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Random Walk'}), (b:Concept {name: 'White Noise'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Backward Shift Operator', definition: 'Operator B such that Bx_t = x_{t-1}; used in AR/MA notation.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Backward Shift Operator'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Backward Shift Operator'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Backward Shift Operator'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Serial Correlation (ACF)', definition: 'Autocorrelation of a series with its own lags; informs AR/MA order selection.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Serial Correlation (ACF)'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Serial Correlation (ACF)'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Serial Correlation (ACF)'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Correlogram', definition: 'Plot of ACF values vs lag; visual tool for selecting ARMA p/q.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Correlogram'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Correlogram'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Correlogram'}), (b:Concept {name: 'Serial Correlation (ACF)'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Partial Autocorrelation', definition: 'ACF with removed intermediate-lag effects; helps identify AR order.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Partial Autocorrelation'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Partial Autocorrelation'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Partial Autocorrelation'}), (b:Concept {name: 'Serial Correlation (ACF)'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Akaike Information Criterion', definition: 'AIC = 2k - 2ln(L); penalizes model complexity for order selection.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Akaike Information Criterion'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Akaike Information Criterion'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Akaike Information Criterion'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'AR(p)', definition: 'Autoregressive model x_t = phi1 x_{t-1} + ... + phip x_{t-p} + w_t.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'AR(p)'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'AR(p)'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'AR(p)'}), (b:Concept {name: 'White Noise'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'AR(p)'}), (b:Concept {name: 'Backward Shift Operator'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'MA(q)', definition: 'Moving-average model x_t = w_t + theta1 w_{t-1} + ... + thetaq w_{t-q}.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'MA(q)'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'MA(q)'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'MA(q)'}), (b:Concept {name: 'White Noise'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'MA(q)'}), (b:Concept {name: 'Backward Shift Operator'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'ARMA(p,q)', definition: 'Combined AR + MA model; requires stationary series.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'ARMA(p,q)'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'ARMA(p,q)'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'ARMA(p,q)'}), (b:Concept {name: 'AR(p)'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'ARMA(p,q)'}), (b:Concept {name: 'MA(q)'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'ARIMA(p,d,q)', definition: 'ARMA with d differencing steps to handle non-stationary series.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'ARIMA(p,d,q)'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'ARIMA(p,d,q)'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'ARIMA(p,d,q)'}), (b:Concept {name: 'ARMA(p,q)'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'ARIMA(p,d,q)'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Volatility Clustering', definition: 'Large vol changes tend to be followed by large vol changes; basis for ARCH/GARCH.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Volatility Clustering'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Volatility Clustering'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Volatility Clustering'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Conditional Heteroskedasticity', definition: 'Volatility depends on past shocks and past vol; captured by ARCH family.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Conditional Heteroskedasticity'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Conditional Heteroskedasticity'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Conditional Heteroskedasticity'}), (b:Concept {name: 'Volatility Clustering'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'ARCH', definition: 'Autoregressive Conditional Heteroskedasticity: sigma2_t = omega + alpha eps2_{t-1}.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'ARCH'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'ARCH'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'ARCH'}), (b:Concept {name: 'Conditional Heteroskedasticity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Cointegration', definition: 'Two non-stationary series with a stationary linear combination; basis for pairs trading.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Cointegration'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Cointegration'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Cointegration'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Augmented Dickey-Fuller Test', definition: 'Statistical test for unit root / stationarity (ADF).', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Augmented Dickey-Fuller Test'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Augmented Dickey-Fuller Test'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Augmented Dickey-Fuller Test'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Johansen Test', definition: 'Multivariate cointegration test; determines rank of common stochastic trend.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Johansen Test'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Johansen Test'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Johansen Test'}), (b:Concept {name: 'Cointegration'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'State-Space Model', definition: 'Linear-Gaussian latent dynamics: x_{t+1} = A x_t + B eps_x, y_t = C x_t + D eps_y.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'State-Space Model'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'State-Space Model'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'State-Space Model'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Kalman Filter', definition: 'Recursive estimator for state-space models; predict + update steps.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Kalman Filter'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Kalman Filter'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Kalman Filter'}), (b:Concept {name: 'State-Space Model'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Dynamic Hedge Ratio', definition: 'Kalman-estimated time-varying beta used to hedge a basket vs market.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Dynamic Hedge Ratio'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Dynamic Hedge Ratio'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Dynamic Hedge Ratio'}), (b:Concept {name: 'Kalman Filter'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Markov Regime Model', definition: 'Hidden state switches between regimes; volatility/mean depend on regime.', category: 'time_series_analysis', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Markov Regime Model'}), (cat:Category {name: 'time_series_analysis'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Markov Regime Model'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Markov Regime Model'}), (b:Concept {name: 'State-Space Model'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Bias-Variance Tradeoff', definition: 'Total error = bias^2 + variance + irreducible noise; governs model capacity.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Bias-Variance Tradeoff'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Bias-Variance Tradeoff'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Cross-Validation', definition: 'Partition data to estimate out-of-sample performance; k-fold variant.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Cross-Validation'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Cross-Validation'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Cross-Validation'}), (b:Concept {name: 'Bias-Variance Tradeoff'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'K-Fold Cross-Validation', definition: 'Split data into k folds, train on k-1, evaluate on 1, rotate.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'K-Fold Cross-Validation'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'K-Fold Cross-Validation'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'K-Fold Cross-Validation'}), (b:Concept {name: 'Cross-Validation'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Walk-Forward Analysis', definition: 'Train on expanding window, test on next fold in chronological order (no lookahead).', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Walk-Forward Analysis'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Walk-Forward Analysis'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Walk-Forward Analysis'}), (b:Concept {name: 'Cross-Validation'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Decision Tree', definition: 'Greedy hierarchical splits minimizing impurity; interpretable baseline.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Decision Tree'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Decision Tree'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Decision Tree'}), (b:Concept {name: 'Bias-Variance Tradeoff'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Random Forest', definition: 'Bootstrap-aggregated decision trees; reduces variance vs single tree.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Random Forest'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Random Forest'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Random Forest'}), (b:Concept {name: 'Decision Tree'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Gradient Boosting', definition: 'Sequential ensemble adding weak learners that fit residuals; strong tabular baseline.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Gradient Boosting'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Gradient Boosting'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Gradient Boosting'}), (b:Concept {name: 'Decision Tree'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Support Vector Machine', definition: 'Max-margin linear classifier; kernel trick adds nonlinearity.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Support Vector Machine'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Support Vector Machine'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Support Vector Machine'}), (b:Concept {name: 'Cross-Validation'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Kernel Trick', definition: 'Implicitly map features to higher dimension via kernel function, enabling nonlinear SVM.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Kernel Trick'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Kernel Trick'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Kernel Trick'}), (b:Concept {name: 'Support Vector Machine'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'K-Means Clustering', definition: 'Partition observations into k clusters minimizing within-cluster variance.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'K-Means Clustering'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'K-Means Clustering'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'TF-IDF', definition: 'Term frequency x inverse document frequency weighting for text features.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'TF-IDF'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'TF-IDF'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Document Classification', definition: 'Assign text documents to categories using vectorized features + classifier.', category: 'machine_learning_trading', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Document Classification'}), (cat:Category {name: 'machine_learning_trading'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Document Classification'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Document Classification'}), (b:Concept {name: 'TF-IDF'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Buy & Hold Benchmark', definition: 'Baseline strategy: buy and hold an asset, measure all active strategies against it.', category: 'qstrader_strategies', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Buy & Hold Benchmark'}), (cat:Category {name: 'qstrader_strategies'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Buy & Hold Benchmark'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'S&P500 Momentum', definition: 'Momentum strategy on S&P500 index; long when recent returns positive.', category: 'qstrader_strategies', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'S&P500 Momentum'}), (cat:Category {name: 'qstrader_strategies'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'S&P500 Momentum'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'S&P500 Momentum'}), (b:Concept {name: 'ARMA(p,q)'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Cointegrated Pairs Trading', definition: 'Trade the stationary spread of cointegrated series; long/short per z-score.', category: 'qstrader_strategies', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Cointegrated Pairs Trading'}), (cat:Category {name: 'qstrader_strategies'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Cointegrated Pairs Trading'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Cointegrated Pairs Trading'}), (b:Concept {name: 'Cointegration'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'Cointegrated Pairs Trading'}), (b:Concept {name: 'Johansen Test'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'Intraday Mean Reversion', definition: 'Buy intraday dips / sell intraday pops on a liquid intraday ticker.', category: 'qstrader_strategies', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'Intraday Mean Reversion'}), (cat:Category {name: 'qstrader_strategies'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Intraday Mean Reversion'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'Intraday Mean Reversion'}), (b:Concept {name: 'Stationarity'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'ML Predictive Strategy', definition: 'Use ML model to predict next-day return; position by sign/confidence.', category: 'qstrader_strategies', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'ML Predictive Strategy'}), (cat:Category {name: 'qstrader_strategies'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'ML Predictive Strategy'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'ML Predictive Strategy'}), (b:Concept {name: 'Walk-Forward Analysis'}) MERGE (b)-[:PREREQ_OF]->(a);
MATCH (a:Concept {name: 'ML Predictive Strategy'}), (b:Concept {name: 'Random Forest'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Concept {name: 'News Sentiment Strategy', definition: 'Long/short based on headline sentiment; hedge with market beta.', category: 'qstrader_strategies', source_book: 'aat-2017'});
MATCH (c:Concept {name: 'News Sentiment Strategy'}), (cat:Category {name: 'qstrader_strategies'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'News Sentiment Strategy'}), (b:Book {id: 'aat-2017'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (a:Concept {name: 'News Sentiment Strategy'}), (b:Concept {name: 'Document Classification'}) MERGE (b)-[:PREREQ_OF]->(a);
MERGE (:Formula {id: 'f_bayes_rule', name: 'Bayes\' Rule', expression: 'P(A|B) = P(B|A) * P(A) / P(B)', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_bayes_rule'}), (c:Concept {name: 'Bayes\' Rule'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_bayes_rule'}), (p:Parameter {name: 'P(A)'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_bayes_rule'}), (p:Parameter {name: 'P(B|A)'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_bayes_rule'}), (p:Parameter {name: 'P(B)'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_beta_posterior', name: 'Beta Posterior', expression: 'Beta(alpha + y, beta + n - y) = Beta(alpha + sum success, beta + sum failures)', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_beta_posterior'}), (c:Concept {name: 'Beta-Binomial Model'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_beta_posterior'}), (p:Parameter {name: 'alpha'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_beta_posterior'}), (p:Parameter {name: 'beta'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_beta_posterior'}), (p:Parameter {name: 'n'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_beta_posterior'}), (p:Parameter {name: 'y'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_ar_model', name: 'AR Model', expression: 'x_t = phi_1 x_{t-1} + ... + phi_p x_{t-p} + w_t', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_ar_model'}), (c:Concept {name: 'AR(p)'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_ar_model'}), (p:Parameter {name: 'phi_1..phi_p'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_ar_model'}), (p:Parameter {name: 'w_t'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_ma_model', name: 'MA Model', expression: 'x_t = w_t + theta_1 w_{t-1} + ... + theta_q w_{t-q}', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_ma_model'}), (c:Concept {name: 'MA(q)'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_ma_model'}), (p:Parameter {name: 'theta_1..theta_q'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_ma_model'}), (p:Parameter {name: 'w_t'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_arma_model', name: 'ARMA Model', expression: 'x_t = sum(phi_i x_{t-i}) + sum(theta_j w_{t-j}) + w_t', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_arma_model'}), (c:Concept {name: 'ARMA(p,q)'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_arma_model'}), (p:Parameter {name: 'phi_1..phi_p'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arma_model'}), (p:Parameter {name: 'theta_1..theta_q'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arma_model'}), (p:Parameter {name: 'w_t'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_arima_model', name: 'ARIMA Model', expression: 'differenced ARMA: y_t = x_t - x_{t-1}, then ARMA on y_t', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_arima_model'}), (c:Concept {name: 'ARIMA(p,d,q)'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_arima_model'}), (p:Parameter {name: 'd'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arima_model'}), (p:Parameter {name: 'phi'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arima_model'}), (p:Parameter {name: 'theta'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arima_model'}), (p:Parameter {name: 'w_t'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_arch_model', name: 'ARCH Model', expression: 'sigma2_t = omega + alpha_1 eps2_{t-1}', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_arch_model'}), (c:Concept {name: 'ARCH'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_arch_model'}), (p:Parameter {name: 'omega'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arch_model'}), (p:Parameter {name: 'alpha_1'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_arch_model'}), (p:Parameter {name: 'eps2_{t-1}'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_acf', name: 'ACF', expression: 'rho_k = Cov(x_t, x_{t-k}) / Var(x_t)', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_acf'}), (c:Concept {name: 'Serial Correlation (ACF)'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_acf'}), (p:Parameter {name: 'rho_k'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_acf'}), (p:Parameter {name: 'k'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_adf_test_statistic', name: 'ADF Test Statistic', expression: 'Delta x_t = theta0 + theta1 x_{t-1} + sum(theta_k Delta x_{t-k}) + eps_t', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_adf_test_statistic'}), (c:Concept {name: 'Augmented Dickey-Fuller Test'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_adf_test_statistic'}), (p:Parameter {name: 'theta0'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_adf_test_statistic'}), (p:Parameter {name: 'theta1'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_adf_test_statistic'}), (p:Parameter {name: 'eps_t'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_kalman_predict', name: 'Kalman Predict', expression: 'x_{t+1} = A x_t + B eps_x   (predict)', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_kalman_predict'}), (c:Concept {name: 'Kalman Filter'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_kalman_predict'}), (p:Parameter {name: 'A'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_kalman_predict'}), (p:Parameter {name: 'B'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_kalman_predict'}), (p:Parameter {name: 'eps_x'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_kalman_update', name: 'Kalman Update', expression: 'x_t = x_predicted_t + K_t (y_t - C x_predicted_t)', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_kalman_update'}), (c:Concept {name: 'Kalman Filter'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_kalman_update'}), (p:Parameter {name: 'K_t'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_kalman_update'}), (p:Parameter {name: 'C'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_kalman_update'}), (p:Parameter {name: 'y_t'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_bias-variance', name: 'Bias-Variance', expression: 'E[(y - fhat)^2] = bias^2 + variance + irreducible noise', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_bias-variance'}), (c:Concept {name: 'Bias-Variance Tradeoff'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_bias-variance'}), (p:Parameter {name: 'bias'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_bias-variance'}), (p:Parameter {name: 'variance'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_bias-variance'}), (p:Parameter {name: 'noise'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_svm_primal', name: 'SVM Primal', expression: 'min 1/2||w||^2 + C * sum(max(0, 1 - y_i (w.x_i + b)))', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_svm_primal'}), (c:Concept {name: 'Support Vector Machine'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_svm_primal'}), (p:Parameter {name: 'w'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_svm_primal'}), (p:Parameter {name: 'b'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_svm_primal'}), (p:Parameter {name: 'C'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_svm_primal'}), (p:Parameter {name: 'x_i'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_svm_primal'}), (p:Parameter {name: 'y_i'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_k-means_objective', name: 'K-Means Objective', expression: 'min sum_i ||x_i - mu_{k(i)}||^2', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_k-means_objective'}), (c:Concept {name: 'K-Means Clustering'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_k-means_objective'}), (p:Parameter {name: 'mu_k'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_k-means_objective'}), (p:Parameter {name: 'x_i'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Formula {id: 'f_tf-idf', name: 'TF-IDF', expression: 'tfidf(t,d) = tf(t,d) * log(N / df(t))', source_book: 'aat-2017'});
MATCH (f:Formula {id: 'f_tf-idf'}), (c:Concept {name: 'TF-IDF'}) MERGE (c)-[:HAS_FORMULA]->(f);
MATCH (f:Formula {id: 'f_tf-idf'}), (p:Parameter {name: 'tf'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_tf-idf'}), (p:Parameter {name: 'df'}) MERGE (f)-[:USES_PARAM]->(p);
MATCH (f:Formula {id: 'f_tf-idf'}), (p:Parameter {name: 'N'}) MERGE (f)-[:USES_PARAM]->(p);
MERGE (:Concept {name: 'Futures Contract', definition: 'Standardized exchange-traded contract to buy/sell underlying at a future date at a fixed price.', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Futures Contract'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Futures Contract'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Basis', definition: 'Spot price minus futures price; converges to zero at delivery (cost-of-carry).', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Basis'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Basis'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Cost of Carry', definition: 'Futures price = spot + cost of carry (interest, storage, income yield).', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Cost of Carry'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Cost of Carry'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Binomial Tree', definition: 'Discrete-time lattice approximation of the underlying; used to price options at each node.', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Binomial Tree'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Binomial Tree'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Swap Valuation', definition: 'Value a swap as difference between fixed and floating leg present values; new swap has zero value at initiation.', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Swap Valuation'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Swap Valuation'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Value-at-Risk', definition: 'Loss threshold at a confidence level over a horizon; VaR_p = sqrt(V*R*V^T).', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Value-at-Risk'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Value-at-Risk'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Expected Shortfall', definition: 'Average loss beyond the VaR quantile; coherent risk measure.', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Expected Shortfall'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Expected Shortfall'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Credit VaR', definition: 'Portfolio credit risk VaR accounting for default correlation and recovery rates.', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Credit VaR'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Credit VaR'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Early Assignment Risk', definition: 'American-style contracts may be exercised early, disrupting covered-call income. Hull recommends avoiding the deepest ITM strikes.', category: 'derivatives_markets', source_book: 'hull-8ed'});
MATCH (c:Concept {name: 'Early Assignment Risk'}), (cat:Category {name: 'derivatives_markets'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Early Assignment Risk'}), (b:Book {id: 'hull-8ed'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Market Microstructure', definition: 'Market mechanics: who trades, how orders match, clears and settles.', category: 'market_microstructure', source_book: 'tradmarkets'});
MATCH (c:Concept {name: 'Market Microstructure'}), (cat:Category {name: 'market_microstructure'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Market Microstructure'}), (b:Book {id: 'tradmarkets'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Order Book', definition: 'Central limit order book; limit orders queue by price/time priority.', category: 'market_microstructure', source_book: 'tradmarkets'});
MATCH (c:Concept {name: 'Order Book'}), (cat:Category {name: 'market_microstructure'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Order Book'}), (b:Book {id: 'tradmarkets'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Settlement', definition: 'Transfer of cash + securities after trade execution (T+1/T+2).', category: 'market_microstructure', source_book: 'tradmarkets'});
MATCH (c:Concept {name: 'Settlement'}), (cat:Category {name: 'market_microstructure'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Settlement'}), (b:Book {id: 'tradmarkets'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Clearing', definition: 'Risk-mitigating netting/guarantee step between execution and settlement.', category: 'market_microstructure', source_book: 'tradmarkets'});
MATCH (c:Concept {name: 'Clearing'}), (cat:Category {name: 'market_microstructure'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Clearing'}), (b:Book {id: 'tradmarkets'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Payment System', definition: 'Transfer of funds: RTGS vs deferred net settlement.', category: 'market_microstructure', source_book: 'tradmarkets'});
MATCH (c:Concept {name: 'Payment System'}), (cat:Category {name: 'market_microstructure'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Payment System'}), (b:Book {id: 'tradmarkets'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Private Equity', definition: 'Illiquid equity in private companies; capitalize on operational improvement + leverage.', category: 'alternativeinstruments', source_book: 'alternativeinstruments'});
MATCH (c:Concept {name: 'Private Equity'}), (cat:Category {name: 'alternativeinstruments'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Private Equity'}), (b:Book {id: 'alternativeinstruments'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Hedge Fund', definition: 'Actively managed pooled vehicle; absolute-return mandate via long/short, leverage, derivatives.', category: 'alternativeinstruments', source_book: 'alternativeinstruments'});
MATCH (c:Concept {name: 'Hedge Fund'}), (cat:Category {name: 'alternativeinstruments'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Hedge Fund'}), (b:Book {id: 'alternativeinstruments'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Private Credit', definition: 'Direct lending to private borrowers; illiquid but historically low default.', category: 'alternativeinstruments', source_book: 'alternativeinstruments'});
MATCH (c:Concept {name: 'Private Credit'}), (cat:Category {name: 'alternativeinstruments'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Private Credit'}), (b:Book {id: 'alternativeinstruments'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Securitization', definition: 'Pooling assets into tranches (senior/mezzanine/equity) and selling claims on cashflows.', category: 'alternativeinstruments', source_book: 'alternativeinstruments'});
MATCH (c:Concept {name: 'Securitization'}), (cat:Category {name: 'alternativeinstruments'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Securitization'}), (b:Book {id: 'alternativeinstruments'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Real Assets', definition: 'Real estate, infrastructure, commodities; income + inflation hedge.', category: 'alternativeinstruments', source_book: 'alternativeinstruments'});
MATCH (c:Concept {name: 'Real Assets'}), (cat:Category {name: 'alternativeinstruments'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Real Assets'}), (b:Book {id: 'alternativeinstruments'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Digital Assets', definition: 'Cryptocurrencies and blockchain-native instruments; high vol, nascent liquidity.', category: 'alternativeinstruments', source_book: 'alternativeinstruments'});
MATCH (c:Concept {name: 'Digital Assets'}), (cat:Category {name: 'alternativeinstruments'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Digital Assets'}), (b:Book {id: 'alternativeinstruments'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Credit Default', definition: 'Counterparty fails to meet a debt obligation in full or on time.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Credit Default'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Credit Default'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Probability of Default (PD)', definition: 'Likelihood a counterparty defaults within a horizon; drives expected loss.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Probability of Default (PD)'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Probability of Default (PD)'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Loss Given Default (LGD)', definition: 'Share of exposure lost given default (1 - recovery rate).', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Loss Given Default (LGD)'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Loss Given Default (LGD)'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Exposure at Default (EAD)', definition: 'Amount exposed to a counterparty at the time of default.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Exposure at Default (EAD)'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Exposure at Default (EAD)'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Recovery Rate', definition: 'Fraction of claim recovered after default; seniority and collateral determine it.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Recovery Rate'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Recovery Rate'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Credit Value Adjustment (CVA)', definition: 'Adjust derivative value for counterparty credit risk: EAD * PD * LGD contribution.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Credit Value Adjustment (CVA)'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Credit Value Adjustment (CVA)'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Debt Value Adjustment (DVA)', definition: 'Adjustment for own credit risk; counterparty benefits when we might default.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Debt Value Adjustment (DVA)'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Debt Value Adjustment (DVA)'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Funding Value Adjustment (FVA)', definition: 'Adjustment for funding cost of a trade; higher when unsecured funding is unavailable.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Funding Value Adjustment (FVA)'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Funding Value Adjustment (FVA)'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Collateral / Margining', definition: 'Posting collateral or margin to reduce credit exposure between counterparties.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Collateral / Margining'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Collateral / Margining'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Credit Rating', definition: 'Agency opinion of creditworthiness; ordinal mapping to PD.', category: 'credit_financing', source_book: 'credit_risk'});
MATCH (c:Concept {name: 'Credit Rating'}), (cat:Category {name: 'credit_financing'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Credit Rating'}), (b:Book {id: 'credit_risk'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Funding Liquidity', definition: 'Ease of obtaining cash for day-to-day obligations (rollover/redemption).', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Funding Liquidity'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Funding Liquidity'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Market Liquidity', definition: 'Ease of trading an asset without moving its price (tight spread, deep book).', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Market Liquidity'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Market Liquidity'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Liquidity Spiral', definition: 'Feedback loop: falling prices force selling that depresses prices further (Fisher dynamics).', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Liquidity Spiral'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Liquidity Spiral'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Market Impact', definition: 'Price movement caused by own trading; power-law function of order size.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Market Impact'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Market Impact'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Liquidity-Adjusted VaR', definition: 'VaR augmented by liquidation-cost term; captures slow-exit risk.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Liquidity-Adjusted VaR'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Liquidity-Adjusted VaR'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Extreme Value Theory', definition: 'Statistical theory of tail events; used to model liquidity shocks and EVT-based VaR.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Extreme Value Theory'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Extreme Value Theory'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Hawkes Process', definition: 'Self-exciting point process that clusters jumps; models liquidity crisis arrivals.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Hawkes Process'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Hawkes Process'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Basel III', definition: 'Banking regulation emphasizing capital + liquidity (LCR, NSFR).', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Basel III'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Basel III'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Liquidity Coverage Ratio (LCR)', definition: 'High-quality liquid assets / 30-day net cash outflows must exceed 100%.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Liquidity Coverage Ratio (LCR)'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Liquidity Coverage Ratio (LCR)'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Net Stable Funding Ratio (NSFR)', definition: 'Available stable funding / required stable funding over a 1-year horizon.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Net Stable Funding Ratio (NSFR)'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Net Stable Funding Ratio (NSFR)'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Stress Testing', definition: 'Scenario-based assessment of capital/liquidity under adverse conditions.', category: 'liquidity_regulation', source_book: 'liquidity_regulation'});
MATCH (c:Concept {name: 'Stress Testing'}), (cat:Category {name: 'liquidity_regulation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Stress Testing'}), (b:Book {id: 'liquidity_regulation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Model Risk', definition: 'Risk of loss from using a model that is wrong, mis-specified, or misused.', category: 'model_risk', source_book: 'model_failure'});
MATCH (c:Concept {name: 'Model Risk'}), (cat:Category {name: 'model_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Model Risk'}), (b:Book {id: 'model_failure'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Model Validation', definition: 'Independent review confirming a model is conceptually sound and workable.', category: 'model_risk', source_book: 'model_failure'});
MATCH (c:Concept {name: 'Model Validation'}), (cat:Category {name: 'model_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Model Validation'}), (b:Book {id: 'model_failure'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Model Governance', definition: 'Policies/roles ensuring models are approved, documented and monitored.', category: 'model_risk', source_book: 'model_failure'});
MATCH (c:Concept {name: 'Model Governance'}), (cat:Category {name: 'model_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Model Governance'}), (b:Book {id: 'model_failure'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Contagion', definition: 'Transmission of stress across institutions/markets via direct or indirect channels.', category: 'model_risk', source_book: 'model_failure'});
MATCH (c:Concept {name: 'Contagion'}), (cat:Category {name: 'model_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Contagion'}), (b:Book {id: 'model_failure'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Crisis Anatomy', definition: 'Phases of a financial crisis: build-up, trigger, propagation, resolution.', category: 'model_risk', source_book: 'model_failure'});
MATCH (c:Concept {name: 'Crisis Anatomy'}), (cat:Category {name: 'model_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Crisis Anatomy'}), (b:Book {id: 'model_failure'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Stress-Testing & VaR Validation', definition: 'Backtesting and critiquing VaR models; validating tail-risk forecasts.', category: 'model_risk', source_book: 'model_failure'});
MATCH (c:Concept {name: 'Stress-Testing & VaR Validation'}), (cat:Category {name: 'model_risk'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Stress-Testing & VaR Validation'}), (b:Book {id: 'model_failure'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Realized Volatility', definition: 'Sample standard deviation of returns over a horizon; the empirical vol.', category: 'volatility_correlation', source_book: 'volatility_correlation'});
MATCH (c:Concept {name: 'Realized Volatility'}), (cat:Category {name: 'volatility_correlation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Realized Volatility'}), (b:Book {id: 'volatility_correlation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'EWMA Volatility', definition: 'Exponentially weighted moving-average of squared returns; lambda=0.94 is RiskMetrics standard.', category: 'volatility_correlation', source_book: 'volatility_correlation'});
MATCH (c:Concept {name: 'EWMA Volatility'}), (cat:Category {name: 'volatility_correlation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'EWMA Volatility'}), (b:Book {id: 'volatility_correlation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'DCC-GARCH', definition: 'Dynamic Conditional Correlation GARCH; models time-varying correlations between assets.', category: 'volatility_correlation', source_book: 'volatility_correlation'});
MATCH (c:Concept {name: 'DCC-GARCH'}), (cat:Category {name: 'volatility_correlation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'DCC-GARCH'}), (b:Book {id: 'volatility_correlation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Copula', definition: 'Multivariate dependence function coupling marginal distributions; used for correlated defaults/returns.', category: 'volatility_correlation', source_book: 'volatility_correlation'});
MATCH (c:Concept {name: 'Copula'}), (cat:Category {name: 'volatility_correlation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Copula'}), (b:Book {id: 'volatility_correlation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Volatility-Correlation Nexus', definition: 'In stress, asset correlations rise toward 1 (diversification fails), amplifying tail risk.', category: 'volatility_correlation', source_book: 'volatility_correlation'});
MATCH (c:Concept {name: 'Volatility-Correlation Nexus'}), (cat:Category {name: 'volatility_correlation'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Volatility-Correlation Nexus'}), (b:Book {id: 'volatility_correlation'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Leverage Effect', definition: 'Volatility is lower in rising markets and higher in falling markets; negative equity-vol feedback.', category: 'module5', source_book: 'module5'});
MATCH (c:Concept {name: 'Leverage Effect'}), (cat:Category {name: 'module5'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Leverage Effect'}), (b:Book {id: 'module5'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Non-Linearity', definition: 'Portfolio responses and hedge ratios are nonlinear in the underlying; gamma captures it.', category: 'module5', source_book: 'module5'});
MATCH (c:Concept {name: 'Non-Linearity'}), (cat:Category {name: 'module5'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Non-Linearity'}), (b:Book {id: 'module5'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Non-Linear Mean Reversion', definition: 'Mean reversion is stronger at wider departures: speed of reversion grows with distance.', category: 'module5', source_book: 'module5'});
MATCH (c:Concept {name: 'Non-Linear Mean Reversion'}), (cat:Category {name: 'module5'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Non-Linear Mean Reversion'}), (b:Book {id: 'module5'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Retrieval-Augmented Generation', definition: 'Retrieve relevant external knowledge then generate grounded responses; reduces hallucination.', category: 'rag_systems', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'Retrieval-Augmented Generation'}), (cat:Category {name: 'rag_systems'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Retrieval-Augmented Generation'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'GraphRAG', definition: 'RAG over a knowledge graph: retrieve via fulltext/vector, then graph-expand neighborhoods for context.', category: 'rag_systems', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'GraphRAG'}), (cat:Category {name: 'rag_systems'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'GraphRAG'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Embeddings', definition: 'Dense vector representations of text; distance encodes semantic similarity.', category: 'rag_systems', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'Embeddings'}), (cat:Category {name: 'rag_systems'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Embeddings'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Vector Search', definition: 'Nearest-neighbour retrieval over embedding vectors (cosine / euclidean).', category: 'rag_systems', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'Vector Search'}), (cat:Category {name: 'rag_systems'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Vector Search'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Agent Orchestration', definition: 'Coordinating specialised agents: task routing, roles, inter-agent communication, fallbacks.', category: 'agents_orchestration', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'Agent Orchestration'}), (cat:Category {name: 'agents_orchestration'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Agent Orchestration'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'ReAct', definition: 'Interleave reasoning (thought), acting (tool calls), and observing results.', category: 'agents_orchestration', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'ReAct'}), (cat:Category {name: 'agents_orchestration'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'ReAct'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MERGE (:Concept {name: 'Tool Use', definition: 'Agents call external functions (APIs, calculators, DBs) as actions that shape reasoning.', category: 'agents_orchestration', source_book: 'buildingagents'});
MATCH (c:Concept {name: 'Tool Use'}), (cat:Category {name: 'agents_orchestration'}) MERGE (c)-[:BELONGS_TO]->(cat);
MATCH (c:Concept {name: 'Tool Use'}), (b:Book {id: 'buildingagents'}) MERGE (b)-[:HAS_CHAPTER]->(c);
MATCH (s:Strategy {name: 'Buy & Hold Benchmark'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.5}]->(r);
MATCH (s:Strategy {name: 'S&P500 Momentum'}), (r:Regime {name: 'Trending'}) MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name: 'S&P500 Momentum'}), (r:Regime {name: 'Recovery'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'Cointegrated Pairs Trading'}), (r:Regime {name: 'MeanReverting'}) MERGE (s)-[:ACTIVATED_BY {weight:0.8}]->(r);
MATCH (s:Strategy {name: 'Intraday Mean Reversion'}), (r:Regime {name: 'MeanReverting'}) MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name: 'ML Predictive Strategy'}), (r:Regime {name: 'Trending'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'ML Predictive Strategy'}), (r:Regime {name: 'Neutral'}) MERGE (s)-[:ACTIVATED_BY {weight:0.5}]->(r);
MATCH (s:Strategy {name: 'News Sentiment Strategy'}), (r:Regime {name: 'Crisis'}) MERGE (s)-[:ACTIVATED_BY {weight:0.7}]->(r);
MATCH (s:Strategy {name: 'News Sentiment Strategy'}), (r:Regime {name: 'HighVolatility'}) MERGE (s)-[:ACTIVATED_BY {weight:0.6}]->(r);
MATCH (s:Strategy {name: 'S&P500 Momentum'}), (f:Formula {name: 'ARMA Model'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name: 'S&P500 Momentum'}), (c:Concept {name: 'ARMA(p,q)'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Cointegrated Pairs Trading'}), (f:Formula {name: 'Johansen Test'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name: 'Cointegrated Pairs Trading'}), (c:Concept {name: 'Cointegration'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'Intraday Mean Reversion'}), (f:Formula {name: 'Beta Posterior'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name: 'Intraday Mean Reversion'}), (c:Concept {name: 'Beta-Binomial Model'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'ML Predictive Strategy'}), (f:Formula {name: 'Bias-Variance'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name: 'ML Predictive Strategy'}), (c:Concept {name: 'Walk-Forward Analysis'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (s:Strategy {name: 'News Sentiment Strategy'}), (f:Formula {name: 'TF-IDF'}) MERGE (s)-[:HAS_FORMULA]->(f);
MATCH (s:Strategy {name: 'News Sentiment Strategy'}), (c:Concept {name: 'Document Classification'}) MERGE (s)-[:DERIVED_FROM]->(c);
MATCH (a:Strategy {name: 'Cointegrated Pairs Trading'}), (b:Strategy {name: 'Factor Momentum Rotation'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'Intraday Mean Reversion'}), (b:Strategy {name: 'Momentum Breakout'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (a:Strategy {name: 'News Sentiment Strategy'}), (b:Strategy {name: 'Systemic Risk Hedge'}) MERGE (a)-[:CONTRADICTED_BY]->(b);
MATCH (s:Strategy {name: 'Long Variance Swap'}) SET s.tradeable_venue = 'research_only';
MATCH (s:Strategy {name: 'Short Variance Swap'}) SET s.tradeable_venue = 'research_only';
MATCH (s:Strategy {name: 'Transformer Vol Forecast'}) SET s.tradeable_venue = 'research_only';
MATCH (s:Strategy {name: 'Gamma Scalp'}) SET s.tradeable_venue = 'research_only';
MATCH (s:Strategy {name: 'Delta-Neutral Carry'}) SET s.tradeable_venue = 'research_only';
MATCH (s:Strategy {name: 'Vol Surface Arb'}) SET s.tradeable_venue = 'research_only';
MATCH (s:Strategy {name: 'Jump-Filtered Vol Trading'}) SET s.tradeable_venue = 'research_only';
