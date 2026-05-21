# GraphAlpha

> Autonomous xStocks trading agent powered by a financial knowledge graph

**Stack:** Memgraph · FastAPI · Kraken CLI · Speechmatics · Featherless LLM · React · Vultr

---

## Architecture

```
Speechmatics (voice)          Featherless LLM (sentiment)     Market data (price/vol)
        │                              │                               │
        └──────────────────────────────┼───────────────────────────────┘
                                       ▼
                        ┌─────────────────────────────┐
                        │   Memgraph Knowledge Graph   │
                        │  Concepts · Strategies       │
                        │  Formulas · Regimes          │
                        │  Signals · Positions         │
                        └────────────┬────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                 ▼
             Regime detector   Signal engine    Contradiction check
                    │                │                 │
                    └────────────────┼─────────────────┘
                                     ▼
                              Portfolio optimizer
                              (Kelly / Sharpe sizing)
                                     │
                                     ▼
                              Kraken CLI execution
                              (xStocks orders)
                                     │
                                     ▼
                           React admin UI (Vultr)
```

## Repository structure

```
graphalpha/
├── graph/
│   ├── schema/
│   │   └── master.cypher       # ← single source of truth for the KG
│   ├── seeds/
│   │   └── tickers_extended.cypher
│   ├── migrations/
│   └── queries/                # named Cypher queries for agent modules
│       ├── regime_strategies.cypher
│       ├── reasoning_trace.cypher
│       └── signal_leaderboard.cypher
├── agent/
│   ├── signals/                # signal generation modules
│   ├── execution/              # Kraken CLI wrapper
│   └── regime/                 # regime classification
├── api/
│   ├── routes/                 # FastAPI route handlers
│   └── models/                 # Pydantic models
├── frontend/
│   └── src/
│       ├── components/
│       └── pages/
├── infra/
│   ├── docker-compose.yml      # Memgraph + API + frontend
│   └── vultr/                  # Vultr deployment configs
├── scripts/
│   └── csv_to_cypher.py        # converts new concept CSVs to MERGE blocks
├── docs/
│   └── architecture.md
└── README.md
```

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/yourname/graphalpha
cd graphalpha
pip install -r requirements.txt

# 2. Start Memgraph
docker compose up memgraph -d

# 3. Load the knowledge graph
cat graph/schema/master.cypher | mgconsole --host localhost --port 7687

# 4. Verify node counts
python scripts/verify_graph.py

# 5. Start API
uvicorn api.main:app --reload

# 6. Start frontend
cd frontend && npm install && npm run dev
```

## Challenges entered

| Hackathon track | How we qualify |
|----------------|---------------|
| Kraken — Trading PnL | xStocks execution via Kraken CLI |
| Vultr — Enterprise Agent | Full backend deployed on Vultr VM |
| Speechmatics | Earnings call transcription → graph ingestion |
| Featherless | Open-source LLM for sentiment scoring |

## Knowledge graph stats (v0.10.0)

| Element | v0.1.0 | v0.3.0 | v0.5.1 | v0.6.0 | v0.7.0 | v0.8.0 | v0.9.0 | v0.10.0 |
|---------|--------|--------|--------|--------|--------|--------|--------|---------|
| Concept nodes | 29 | 93 | 173 | 201 | 223 | 251 | 286 | **324** |
| Category nodes | 13 | 28 | 34 | 36 | 38 | 40 | 42 | **45** |
| Formula nodes | 16 | 33 | 69 | 79 | 83 | 88 | 95 | **99** |
| Strategy nodes | 5 | 10 | 16 | 18 | 19 | 21 | 23 | **26** |
| Regime nodes | 6 | 7 | 7 | 7 | 7 | 7 | 7 | **7** |
| Ticker nodes | 10 | 10 | 10 | 10 | 10 | 10 | 10 | **10** |
| PREREQ_OF edges | 24 | 115 | ~240 | ~290 | ~335 | ~368 | ~403 | **~445** |
| ACTIVATED_BY edges | 10 | 24 | 33 | 38 | 41 | 41 | 41 | **41** |
| CONTRADICTED_BY edges | 2 | 5 | 14 | 20 | 21 | 23 | 25 | **28** |
| HAS_FORMULA edges | 17 | 58 | ~98 | ~115 | ~125 | ~132 | ~141 | **~149** |
| EVALUATED_BY edges | — | — | 16 | 23 | 23 | 23 | 23 | **23** |
| GENERALIZES_TO edges | — | — | 13 | 22 | 22 | 24 | 26 | **30** |
| MOTIVATES edges | — | — | 9 | 16 | 21 | 24 | 29 | **34** |
| FITTED_TO edges | — | — | — | 10 | 10 | 14 | 14 | **14** |
| TRAINED_BY edges | — | — | 4 | 4 | 4 | 4 | 4 | **4** |
| TRANSMITS_TO edges | — | 6 | 6 | 6 | 6 | 6 | 10 | **12** |
| MONITORS edges | — | 10 | 10 | 10 | 10 | 10 | 10 | **10** |
| REPLICATES_WITH edges | — | — | 5 | 5 | 5 | 5 | 5 | **5** |
| HEDGES edges | — | — | 4 | 4 | 4 | 4 | 4 | **4** |
| **Total relationship types** | **5** | **10** | **16** | **17** | **17** | **17** | **17** | **17** |

**New in v0.10.0 (Dynamic Causal Networks, Causal Inference & BN Applications):**
- 38 concepts: Causal inference / econophysics (Reichenbach Common Cause Principle, Common Cause, Causal Structure of Equity Factors, Factor Redundancy, Knightian Uncertainty, Coherent Portfolio Optimization, Marcenko-Pastur Distribution, Correlation Matrix De-Noising/De-Toning, Econophysics, Quant Meltdown 2007); dynamic causal networks (DYNOTEARS, VARLiNGAM, Intra-Slice Matrix, Inter-Slice Matrix, Causal Edge Threshold, Complex Contagion, Cascade Effect, Causal Intervention, Epidemic Model, Largest Connected Subgraph, Standardized Log Return, Sector Causal Clustering, CausalNex); BN applications (Oil Price BN, Geopolitical Risk Factor, OPEC Supply Factor, Commodity Price Factor BN, BN Credit Scoring, Financial Ratio Node, Bayesian Credit Scorecard, Rating Migration BN, Bayesian PD Update, BN vs Logistic Regression, Macro Regime Conditioning)
- 4 new formula nodes: `f_marcenko_pastur` (Marcenko-Pastur upper/lower edge), `f_standardized_log_return`, `f_var1_dynamic_bn` (VAR(1) intra+inter-slice structural equation), `f_bayesian_pd_update`
- 3 new categories: `causal_inference`, `dynamic_causal_networks`, `bn_applications`
- 3 new strategies: DYNOTEARS Contagion Signal (VARLiNGAM on S&P 100 financials, 2008 crisis causal subgraph); BN Oil Price Signal (OPEC + geopolitical + demand BN); Bayesian Credit Signal (BN PD + Bayesian updating + macro conditioning)
- 12 new agent query patterns (Q57–Q68): DYNOTEARS pipeline, AIG 2008 cascade path, common cause detection, factor redundancy→contagion, coherent portfolio construction, de-noise/de-tone, oil price scenario, BN vs logistic, Bayesian PD monitoring, rating migration conditioning, sector clustering signal, causal intervention stress test

**New in v0.9.0 (Credit Risk, Climate Risk & BN Integration):**
- 35 concepts: Credit risk fundamentals (Probability of Default, Recovery Rate, Loss Given Default, Exposure at Default, Expected Loss, Unexpected Loss, Credit Loss Distribution, Monte Carlo Credit Simulation, Credit VaR, Expected Tail Loss, Credit Portfolio Concentration); structural credit models (Vasicek Credit Model, Merton Model, Three-Factor Credit Model, Asset Correlation, Distance to Default); climate risk taxonomy (Climate Risk, Physical Risk, Transition Risk, Climate Risk Transmission, Stranded Asset, Carbon Price, Net Zero Commitment); sustainable finance (Sustainable Finance, Green Bond, Greenwashing); climate-credit integration (CERM, Climate-Adjusted PD, BN Flood Risk Model, GIS Integration, BN Sensitivity Analysis, Expert Elicitation)
- 7 new formula nodes: `f_expected_loss` (EL = Σ PD·EAD·LGD), `f_lgd` (LGD = 1−RR), `f_vasicek_pd` (conditional PD), `f_vasicek_var` (Vasicek loss quantile), `f_credit_etl` (ETL), `f_merton_dd` (distance to default), `f_mc_credit_loss` (MCS per-scenario loss)
- 2 new categories: `credit_risk`, `climate_risk`
- 2 new strategies: Climate Credit Risk Overlay (CERM + RCP scenarios + climate-adjusted PD); BN Physical Risk Signal (GIS-BN flood risk → real estate/insurance/infrastructure exposure cuts)
- 4 new TRANSMITS_TO edges linking climate → credit → systemic risk
- 10 new agent query patterns (Q47–Q56): full credit loss pipeline, Vasicek VaR path, Merton→Vasicek derivation, climate→credit transmission, BN flood pipeline, green finance legitimacy, three-factor vs Vasicek, climate stress scenario, ETL vs Credit VaR, net-zero alignment signal

**New in v0.8.0 (BN Structure & Parameter Learning):**
- 28 concepts across advanced BN topology (D-Separation, Markov Blanket, Active Path, V-Structure, Explaining Away, Plate Notation, Naive Bayes Classifier), dynamic BNs (Dynamic Bayesian Network, Hidden Markov Model, Transition Model, Emission Model), and structure learning (Structure Learning, Score-Based, Constraint-Based, K2 Algorithm, K2 Score, BIC Score, BDeu Score, BDs Score, Hill Climb Search, Maximum Likelihood Estimator, Bayesian Parameter Estimation, Equivalence Class, CPDAG, Topological Ordering, Domain Knowledge Constraint, BN Simulation, Ancestral Sampling)
- 5 new formula nodes: `f_k2_score`, `f_bic_score`, `f_bdeu_score`, `f_mle_cpd`, `f_hmm_joint`
- 2 new categories: `structure_learning`, `dynamic_bayesian_networks`
- 2 new strategies: Learned BN Macro Regime Signal (K2+HillClimb+MLE pipeline); extended Bayesian Macro Risk Signal linkage to Structure Learning
- 8 new agent query patterns (Q39–Q46): structure learning pipeline, score comparison, HMM regime detection, d-separation independence path, equivalence ambiguity resolution, MLE vs Bayesian parameter estimation, Naive Bayes signal filter, ancestral sampling validation loop

**New in v0.7.0 (Bayesian Networks for Financial Risk):**
- 22 concepts across Bayesian Network structure (DAG, CPT, Factor, Factor Graph, Conditional Independence, Joint Factorization, Distance Matrix, KDE), Bayesian inference quartet (Prior, Likelihood, Evidence, Posterior), exact inference (Variable Elimination, Factor Product, Factor Marginalization, Factor Conditioning, MAP/MPA), approximate inference (Belief Propagation, Message Passing, Direct Sampling, Gibbs Sampling, Weighted Sampling, Importance Sampling), and financial application (Shenoy 1999 Stock Price BN, pgmpy library)
- 4 new formula nodes: `f_bayes`, `f_joint_factorization`, `f_kde`, `f_gibbs`
- 2 new categories: `bayesian_networks`, `probabilistic_inference`
- 1 new strategy: Bayesian Macro Risk Signal (pgmpy VariableElimination; sell signal P(SP=low) > 0.35 given macro conditioning)
- 6 new agent query patterns (Q33–Q38): BN inference chain, factor graph traversal, sampling method selection, prior→posterior update path, Monty Hall contradiction check, financial BN construction path

**New in v0.6.0 (Extreme Value Theory & Asymmetric GARCH):**
- 28 concepts across two new domains: EVT (POT, BMM, GPD, GEV family: Gumbel/Frechet/Weibull, Fisher-Tippett Theorem, MDA, GARCH-EVT combination, GPD estimators: MLE/Hill/Moment, threshold selection, mean excess function, block size selection, GEVMLE, GEV-GPD relationship) · Asymmetric GARCH (EGARCH, GJR-GARCH, APARCH, leverage effect, innovation term, GJR mean reversion condition, APARCH power parameter δ) · Political Risk (5-component framework, dummy variable GARCH, uncertainty premium) · Bagging ensemble, Multi-Head Attention formula completeness
- 10 new formula nodes: `f_egarch`, `f_gjr_garch`, `f_gjr_unconditional`, `f_aparch`, `f_gpd_var`, `f_gpd_es`, `f_gev_cdf`, `f_mean_excess`, `f_mha`, `f_hill`
- 1 new relationship type: `FITTED_TO` (method/estimator → target distribution)
- 9 new `GENERALIZES_TO` edges: APARCH → GARCH/GJR/EGARCH; GEV → Gumbel/Frechet/Weibull
- 2 new strategies: GARCH-EVT VaR Overlay, Asymmetric Vol Regime Signal
- 6 new agent query patterns (Q27–Q32): EVT method selection, GARCH-EVT pipeline, APARCH generalization tree, leverage-to-strategy chain, MDA distribution selection, political risk → vol model path

**New in v0.5.1 (gap-fill & augmentation):**
- 18 concepts: RNN training internals (BPTT, Vanishing Gradient, Exploding Gradient), transformer sublayers (Layer Normalization, Residual Connection, Dropout), GARCH(1,1) baseline, Bipower Variation, Jump Quadratic Variation, Kupiec POF Test, Conditional Coverage Hypothesis, Basel Traffic Light Test, Elicitability, Pinball Loss, Cholesky Decomposition, Ledoit-Wolf Shrinkage, DeepAREstimator, PICP, Calibration
- 7 new formula nodes: `f_garch11`, `f_bipower_variation`, `f_jump_qv`, `f_kupiec_pof`, `f_layer_norm`, `f_picp`, `f_ledoit_wolf`
- 1 new relationship type: `MOTIVATES` (problem → solution, e.g. Vanishing Gradient → LSTM)
- 6 new agent query patterns (Q21–Q26): motivation chain, validation suite, transformer component map, GARCH comparison, portfolio VaR construction path, BV → OS estimator dependency graph

**New in v0.5.0 (deep learning for VaR & transformer vol forecasting):**
- 36 concepts across OS algorithm internals, RNN/GRU/LSTM hierarchy, DeepAR/DeepVaR, probabilistic forecasting, VaR backtesting loss functions (hit, quadratic, smooth, tick, firm), Christoffersen/DQ tests, transformer architecture (attention, MHSA, encoder-decoder, FFN, positional encoding), Multi-Transformer
- 2 new relationship types: `TRAINED_BY` (ML model → optimizer), `EVALUATED_BY` (model → backtest metric)
- 2 new strategies: DeepVaR Risk Overlay, Transformer Vol Forecast
- 5 new agent query patterns (Q16–Q20)

**New in v0.3.0 (systemic risk & macroeconomic indicators):**
- 28 concepts: Systemic Risk, Non-Stationarity, Emergent Property, Fallacy of Composition, Financial Network, Interbank Network, Network Densification, Contagion, Direct/Indirect Exposure, Shadow Banking, Disintermediation, Regulatory Arbitrage, Off-Balance-Sheet Risk, Macro/Microprudential Regulation, Procyclicality, Too-Big-To-Fail, Stress Testing, Scenario Analysis, Fire Sale, Liquidity Spiral, CoVaR, SRISK, Network Centrality, Systemic Importance Score, Financial Stability Monitoring, Systemic Risk Measurement
- 2 new relationship types: `TRANSMITS_TO` (contagion propagation), `MONITORS` (regulatory oversight)
- 2 overlay strategies: Systemic Risk Hedge, Contagion Path Avoidance
- 1 new regime: SystemicStress
- 4 new agent query patterns (Q8–Q11)

**New in v0.2.0:** factor investing, asset pricing, estimation, performance attribution (36 concepts, 3 strategies).
**New in v0.1.0:** options pricing, derivatives, volatility, Greeks (29 concepts, 5 strategies).

**Concept domains covered (cumulative):** Options & Vol · Factor Investing · Estimation · Systemic Risk · Network Theory · Shadow Banking · Fire Sale · Contingent Claims · Granger Causality · Information Theory · Variance Swaps · OTC · Replication Theory · Lévy & Jump Models · Order Statistics · OS Volatility Estimation · Spanning Mechanics · Implicit Vol · RNN/GRU/LSTM · DeepAR/DeepVaR · Probabilistic Forecasting · VaR Backtesting · Transformer Architecture · Attention Mechanism · Bipower Variation · GARCH Baseline · Portfolio VaR Aggregation · Extreme Value Theory (POT/BMM/GPD/GEV) · Asymmetric GARCH (EGARCH/GJR/APARCH) · Leverage Effect · Political Risk · Ensemble Learning (Bagging) · Bayesian Networks (DAG/CPT/Factor Graph) · Bayesian Inference (Prior/Likelihood/Posterior) · Exact Inference (Variable Elimination/MAP) · Approximate Inference (Belief Propagation/Gibbs/Importance Sampling) · BN Structure Learning (K2/HillClimb/BIC/BDeu/BDs) · BN Parameter Estimation (MLE/Bayesian) · Dynamic Bayesian Networks (HMM/DBN) · D-Separation & Markov Blanket · Credit Risk (PD/LGD/EAD/EL/Vasicek/Merton) · Climate Risk (Physical/Transition/CERM) · Sustainable Finance (Green Bonds/ESG) · BN Applied to Disaster & Climate Risk · **Dynamic Causal Networks (DYNOTEARS/VARLiNGAM)** · **Causal Inference & Econophysics (Reichenbach/MPD/De-toning)** · **BN Applications (Oil Price/Credit Scoring/Rating Migration)** · **Coherent Portfolio Optimization (Rebonato-Denev)**

*Runtime nodes (Signal, Position, EarningsEvent, NewsEntity) grow during agent operation.*

---

## Assessment Q&A Bank (WQU Risk Management — Modules 6–8)

These questions were drawn from graded assessments and can be used to:
1. **Validate agent reasoning** — pose them as graph traversal queries
2. **Enrich the graph** — each correct answer encodes a relationship; each wrong option encodes a `CONTRADICTED_BY` or `MOTIVATES` edge
3. **Fine-tune LLM scoring** — use as (question, correct_answer, distractor) triples for RLHF / DPO training on the financial knowledge graph

---

### Module 6 — Bayesian Network Structure & Parameter Learning

**Source: Cooper & Herskovits (K2 paper)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M6-1 | Which two challenges does K2 address with "fundamentally the same" technique? | Missing data and hidden variables | Both treated via marginalization over unobserved states |
| Q-M6-2 | When comparing network posterior probabilities, Cooper & Herskovits do which? | Calculate the ratios of the networks' joint probabilities with the data | Equal priors cancel; only joint P(D,G) ratio remains |
| Q-M6-3 | Under certain conditions, the Dirichlet distribution reduces to which? | Uniform distribution | When all α_ijk = 1; used in K2 derivation |
| Q-M6-4 | What is the key feature of a Bayesian network? | Explicit representation of conditional independence and dependence among events | DAG encodes d-separation structure |

**Source: Schreiber**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M6-5 | Iterating over all triplets to identify conditional independencies is a method of which? | Constraint learning | PC algorithm; contrast with score-based search |
| Q-M6-6 | Chow-Liu tree calculates which quantity between all pairs before finding maximum spanning tree? | Mutual information | I(X;Y); edge weight for tree-structured BN approximation |
| Q-M6-7 | Typical objective functions for BN identification do which? | Balance log probability of data given the model with the complexity of the model | BIC = LL − (d/2)·log(N); penalty prevents overfitting |

**Source: Coscia**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M6-8 | Which is true about cycles? | A cycle is a path that begins and ends with the same node | Walk can revisit nodes; path cannot — key DAG acyclicity definition |
| Q-M6-9 | What is the most common "global" network connectivity information? | The average degree | ⟨k⟩ = 2\|E\|/\|V\|; normalized global summary |
| Q-M6-10 | Which describes most networks from a degree distribution? | There are many orders of magnitude between the minimum and the maximum degree | Heavy-tailed / power-law degree distribution |
| Q-M6-11 | Which are true about connected components? (multi-select) | (1) If two nodes cannot be connected by a path → different components; (2) If two nodes cannot be connected by a walk → different components; (3) Connected components are subgraphs whose nodes can be reached following edges | Real-world networks *do* typically have multiple components — 4th option false |

**Source: pgmpy (M6L4 notebook)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M6-12 | How do we add both marginal and conditional probability distributions in pgmpy? | With the general method add_cpds for both | TabularCPD handles both; add_pds does not exist |
| Q-M6-13 | What must be done to display CPTs? | Convert the CPD object to a DataFrame | Direction: CPD object → DataFrame (not reverse) |
| Q-M6-14 | Which methods were used to learn the network structure? | HillClimbSearch and K2Score | MLE came after for parameter estimation, not structure |
| Q-M6-15 | What does setting X[:,3]=X[:,1] and X[:,6]=X[:,1] accomplish? | Establishes variables 3 and 6 as children of variable 1 | Columns 3 and 6 are fully determined by column 1 → parent-child |

---

### Module 7 — Credit Risk, Climate Risk & BN Applications

**Source: Wu et al. (BN Flood Risk)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M7-1 | "The number of people and impacted infrastructure" is defined as? | Disaster bearer | Three-part taxonomy: driver / environment / bearer |
| Q-M7-2 | "Conditions and surroundings where flood damage occurred" is defined as? | Disaster environment | Physical/geographical context modulating impact |

**Source: Wouters (Climate Credit)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M7-3 | Which are "physical risk drivers"? (multi-select) | Flooding; Drought | Policy = transition risk; sustainability label = transition risk |
| Q-M7-4 | Which are true about Wouters? (multi-select) | (1) Energy label can impact LTV; (2) Physical risk can negatively impact LTV; (3) Energy label can impact PD | Transition risk does NOT decrease EAD — EAD is balance owed |

**Source: quantpi (Vasicek / PD)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M7-5 | Which is generally true about PD? | It varies over time | Dynamic; Bayesian updating as financials change |
| Q-M7-6 | How is the Vasicek threshold defined? | The inverse normal of the unconditional probability of default | C = Φ⁻¹(PD); default when asset return < C |
| Q-M7-7 | In Vasicek with very many borrowers, conditional PD depends only on? | General economic conditions | Idiosyncratic shocks diversify away; only systematic factor Z remains |
| Q-M7-8 | What is the loss rate l(S)? | Loss amount / exposure | Dimensionless fraction; portfolio-level realisation |

**Source: Garnier et al. / BIS / CERM**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M7-9 | Without variance reduction, how many MCS samples to estimate 1-α quantile? | N = 100/α | Ensures ~100 tail observations; α=0.001 → N=100,000 |
| Q-M7-10 | CERM groups can represent? (multi-select) | Geographic region; Economic sector; Rating level | "Climate mitigation strategy" is not a CERM grouping dimension |
| Q-M7-11 | If capital for a loan depends only on that loan's characteristics, model is? | Portfolio invariant | Vasicek property enabling Basel II IRB; ignores concentration risk |

**Source: Spolaor (Approximate Inference)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M7-12 | With small sample sizes, which approximate inference performs well? | Only MCMC (Gibbs) performs well initially | Direct sampling and importance sampling need large N |
| Q-M7-13 | With large sample sizes, which approximate inference methods perform well? | All three (MCMC/Gibbs, Direct Sampling, Weighted Sampling) | Convergence requires large N for all sampling methods |

---

### Module 8 — Dynamic BNs, Causal Structure & Applications

**Source: Alvi (HMM Regime Detection)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-1 | For what is the hmms Python library used? | To identify bull and bear regimes in time-series data | HMM latent states = market regimes |
| Q-M8-2 | What are transitions between hidden states assumed to be? | A first-order Markov chain | P(Xₜ\|Xₜ₋₁) only; memoryless beyond one lag |
| Q-M8-3 | Which Python library "provides fast, flexible, and expressive data structures"? | pandas | Verbatim pandas tagline; used for emission sequence preparation |
| Q-M8-4 | Match regime detection stages (4): | Stage 1: Transform TS → emission sequence; Stage 2: Learn model parameters (Baum-Welch); Stage 3: Find most likely hidden states (Viterbi); Stage 4: Identify latent meaning of each state | Full HMM pipeline |

**Source: Carraro (Gaussian BN Credit Model)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-5 | Which macroeconomic variable is NOT used by Carraro? | Population growth | Uses: Inflation, GDP, Unemployment |
| Q-M8-6 | Which variable has highest arc frequency to PD node? | Non-performing Loans (NPL) | Direct credit quality indicator; stronger than macro variables |
| Q-M8-7 | Which are true about BN graph terminology? (multi-select) | Parents ⊂ Ancestors; Children ⊂ Descendants | Parents are immediate ancestors; children are immediate descendants |

**Source: D'Acunto et al. (Causal Structure of Equity Factors)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-8 | Which is known as the "fear index"? | VIX | CBOE publishes it; measures 30-day implied S&P 500 vol |
| Q-M8-9 | Which is NOT one of the three families of causal structure learning? | Silhouette statistics | Three families: constraint-based, score-based, structural causal models |

**Source: Rebonato & Denev (Coherent Portfolio Optimization)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-10 | Econophysics school believes which? (multi-select) | (1) Exceptional financial events exhibit persistent regularities; (2) Tail behavior of return distributions is stable | Bayesian preference and case-by-case forecasting are Rebonato's own views, not econophysics |
| Q-M8-11 | Markowitz approach does which? | Turns a complex problem of utility maximization into a simple optimization of the variance-return trade-off | Critique: simplification discards tail risk, regimes, expert knowledge |

**Source: Pamfil et al. (DYNOTEARS)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-12 | Dynamic BNs are known in econometrics as? | Structural Vector Autoregressive (SVAR) models | Both capture intra-slice (contemporaneous) + inter-slice (lagged) causal structure |
| Q-M8-13 | When intra-slice weight matrix ordered by sector, what emerges? | An approximately block-diagonal structure | Sector Causal Clustering: within-sector causal weights dominate |

**Source: Coscia (Network Theory)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-14 | Which is a model to describe disease dynamics? | Compartmental (SIR) | Nodes transition: Susceptible → Infected → Recovered |
| Q-M8-15 | Outbreak growth in power-law networks with large hubs is? | Super-exponential | Hubs act as super-spreaders; faster than exponential contagion |

**Source: Dablander & Hinne graph (Z→X, Z→Y)**

| # | Question | Answer | Key Concept |
|---|----------|--------|-------------|
| Q-M8-16 | Which are true about the Z→X, Z→Y graph? (multi-select) | (1) Z is the parent of X and Y; (2) X and Y are descendants of Z | X and Y are NOT spouses (share parent, not child); NOT neighbors in directed sense |

---

## Can Q&A Be Used to Further Train the Graph?

**Yes — three concrete mechanisms:**

### 1. QuizQuestion nodes (new node type)
Each Q&A triple can be stored as a node linked to the concept it tests:

```cypher
MERGE (q:QuizQuestion {id: 'Q-M6-1'})
  SET q.question      = 'Which two challenges does K2 address with fundamentally the same technique?',
      q.correct       = 'Missing data and hidden variables',
      q.distractors   = ['Time complexity and noisy data','Hidden variables and time complexity','Missing data and noisy data'],
      q.source        = 'Cooper & Herskovits 1992',
      q.module        = 'M6',
      q.difficulty    = 'intermediate';

MATCH (q:QuizQuestion {id:'Q-M6-1'}), (c:Concept {name:'K2 Algorithm'})
MERGE (q)-[:TESTS]->(c);
```

### 2. Misconception edges from wrong answers
Distractor options that are plausible-but-wrong encode common confusions:

```cypher
// "Cycle = walk starting and ending at same node" (wrong) → true definition is PATH
MATCH (a:Concept {name:'DAG'}), (b:Concept {name:'Bayesian Network'})
MERGE (a)-[:CONTRADICTED_BY {
  reason: 'Walk can revisit nodes; cycle requires PATH (no repeated nodes) — common misconception',
  quiz_id: 'Q-M6-8'
}]->(b);
```

### 3. LLM fine-tuning dataset
The full bank gives **51 grounded (question, correct_answer, distractor×3) triples** spanning 10 authoritative sources. Formatted as DPO pairs:
- **Chosen**: correct answer + graph-path reasoning
- **Rejected**: each distractor with explanation of why it fails

This trains the Featherless LLM component to reason over the knowledge graph rather than pattern-match surface text.

