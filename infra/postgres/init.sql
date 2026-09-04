-- GraphAlpha PostgreSQL schema

CREATE TABLE IF NOT EXISTS positions (
    id               SERIAL PRIMARY KEY,
    ticker           VARCHAR(20) NOT NULL,
    direction        VARCHAR(10) NOT NULL,
    quantity         NUMERIC(18,6) NOT NULL,
    avg_entry_price  NUMERIC(18,6) NOT NULL,
    current_price    NUMERIC(18,6) NOT NULL DEFAULT 0,
    venue            VARCHAR(20) NOT NULL DEFAULT 'ibkr',
    asset_class      VARCHAR(30) NOT NULL DEFAULT 'equity_xstock',
    status           VARCHAR(10) NOT NULL DEFAULT 'open',
    opened_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at        TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_ticker_open ON positions(ticker) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_ticker  ON positions(ticker);

CREATE TABLE IF NOT EXISTS order_audit (
    id               SERIAL PRIMARY KEY,
    order_id         UUID NOT NULL UNIQUE,
    strategy         VARCHAR(255),
    ticker           VARCHAR(20),
    venue_symbol     VARCHAR(30),
    venue            VARCHAR(20),
    direction        VARCHAR(10),
    quantity         NUMERIC(18,6),
    fill_price       NUMERIC(18,6),
    fee_usd          NUMERIC(12,4),
    mode             VARCHAR(10),
    signal_score     NUMERIC(8,4),
    kelly_fraction   NUMERIC(8,4),
    var_contribution NUMERIC(12,2),
    rejection_reason TEXT,
    raw_response     JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_audit_created ON order_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_audit_ticker  ON order_audit(ticker);

-- ── Financial Engineer chat history (per-screen assistant) ───────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    screen      VARCHAR(40) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_screen ON chat_sessions(screen, created_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    screen      VARCHAR(40) NOT NULL,
    role        VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    sources     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS portfolio_state (
    id              SERIAL PRIMARY KEY,
    cash_balance    NUMERIC(18,2) NOT NULL,
    nav             NUMERIC(18,2) NOT NULL,
    drawdown_pct    NUMERIC(8,4) NOT NULL DEFAULT 0,
    halted          BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed initial portfolio state (10k USD)
INSERT INTO portfolio_state (cash_balance, nav)
VALUES (10000.00, 10000.00)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS backtest_runs (
    id               SERIAL PRIMARY KEY,
    run_id           UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    start_date       DATE,
    end_date         DATE,
    initial_capital  NUMERIC(18,2),
    use_graph        BOOLEAN,
    sharpe_ratio     NUMERIC(8,4),
    calmar_ratio     NUMERIC(8,4),
    max_drawdown     NUMERIC(8,4),
    total_return     NUMERIC(8,4),
    jk_pvalue        NUMERIC(8,6),   -- Jobson-Korkie p-value vs buy-and-hold
    metrics          JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_cycle_log (
    id               SERIAL PRIMARY KEY,
    cycle_id         UUID NOT NULL DEFAULT gen_random_uuid(),
    regime           VARCHAR(50),
    regime_confidence NUMERIC(6,4),
    signals_generated INT,
    orders_approved  INT,
    orders_executed  INT,
    cycle_duration_s NUMERIC(8,2),
    halted           BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shadow_comparison (
    id              SERIAL PRIMARY KEY,
    cycle_id        UUID NOT NULL,
    ticker          VARCHAR(20) NOT NULL,
    strategy        VARCHAR(255),
    signal          JSONB NOT NULL,
    python_decision JSONB,
    cpp_decision    JSONB,
    raw_discrepancy JSONB,
    discrepancy     BOOLEAN GENERATED ALWAYS AS (
                       (python_decision IS NULL AND cpp_decision IS NULL)
                       OR (
                         python_decision->>'action' IS NOT DISTINCT FROM cpp_decision->>'action'
                         AND (
                           python_decision->>'kelly_fraction' IS NULL
                           OR cpp_decision->>'kelly_fraction' IS NULL
                           OR ABS((python_decision->>'kelly_fraction')::float - (cpp_decision->>'kelly_fraction')::float) <= 1e-6
                         )
                         AND (
                           python_decision->>'notional_usd' IS NULL
                           OR cpp_decision->>'notional_usd' IS NULL
                           OR ABS((python_decision->>'notional_usd')::float - (cpp_decision->>'notional_usd')::float) <= 1e-6
                         )
                       )
                     ) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(cycle_id, ticker, strategy)
);

CREATE INDEX IF NOT EXISTS idx_shadow_cycle ON shadow_comparison(cycle_id);
CREATE INDEX IF NOT EXISTS idx_shadow_discrepancy ON shadow_comparison(discrepancy) WHERE discrepancy = false;

-- P7 live validation discrepancy log
CREATE TABLE IF NOT EXISTS live_validation_discrepancy (
    id              SERIAL PRIMARY KEY,
    cycle_id        UUID NOT NULL,
    ticker          VARCHAR(20) NOT NULL,
    strategy        VARCHAR(255),
    paper_price     NUMERIC(18,8),
    live_price      NUMERIC(18,8),
    paper_fee       NUMERIC(12,4),
    live_fee        NUMERIC(12,4),
    paper_slippage  NUMERIC(12,4),
    live_slippage   NUMERIC(12,4),
    discrepancy_type VARCHAR(50),
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_val_cycle ON live_validation_discrepancy(cycle_id);
CREATE INDEX IF NOT EXISTS idx_live_val_ticker ON live_validation_discrepancy(ticker);

-- ResearchAgent edge weight history
CREATE TABLE IF NOT EXISTS kg_edge_snapshots (
    id               SERIAL PRIMARY KEY,
    source           TEXT NOT NULL,
    target           TEXT NOT NULL,
    rel_type         TEXT NOT NULL,
    weight           FLOAT,
    agent_run        TEXT,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_edge_snapshots_recorded ON kg_edge_snapshots(recorded_at);

-- KG edit audit trail
CREATE TABLE IF NOT EXISTS kg_edit_log (
    id                 SERIAL PRIMARY KEY,
    operation          TEXT NOT NULL,
    source             TEXT,
    target             TEXT,
    rel_type           TEXT,
    properties         JSONB,
    validation_passed  BOOLEAN,
    affected_strategies TEXT[],
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Cypher query log
CREATE TABLE IF NOT EXISTS kg_query_log (
    id               SERIAL PRIMARY KEY,
    query_hash       TEXT NOT NULL,
    params           JSONB,
    execution_time_ms INT,
    result_count     INT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Structured agent cycle audit
CREATE TABLE IF NOT EXISTS agent_cycle_audit (
    id               SERIAL PRIMARY KEY,
    cycle_id         UUID NOT NULL,
    timestamp        TIMESTAMPTZ DEFAULT NOW(),
    duration_s       FLOAT,
    regime           TEXT,
    regime_confidence FLOAT,
    sub_agents       JSONB,
    signals          JSONB,
    rejections       JSONB
);

CREATE INDEX IF NOT EXISTS idx_agent_cycle_audit_cycle ON agent_cycle_audit(cycle_id);
CREATE INDEX IF NOT EXISTS idx_agent_cycle_audit_timestamp ON agent_cycle_audit(timestamp DESC);

-- Backtest config templates
CREATE TABLE IF NOT EXISTS backtest_templates (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    params     JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Durable signal archive for export
CREATE TABLE IF NOT EXISTS signal_archive (
    id                       SERIAL PRIMARY KEY,
    signal_id                UUID NOT NULL UNIQUE,
    cycle_id                 UUID,
    timestamp                TIMESTAMPTZ,
    strategy                 TEXT,
    ticker                   TEXT,
    venue                    TEXT,
    venue_symbol             TEXT,
    asset_class              TEXT,
    regime                   TEXT,
    direction                TEXT,
    score                    FLOAT,
    quant_score              FLOAT,
    sentiment_score          FLOAT,
    news_overlay             FLOAT,
    macro_overlay            FLOAT,
    kg_formula_contribution  FLOAT,
    contradiction_blocked    BOOLEAN,
    graph_path               JSONB,
    kelly_fraction           FLOAT,
    var_contribution_pct     FLOAT,
    order_id                 UUID,
    fill_price               FLOAT,
    fill_timestamp           TIMESTAMPTZ,
    slippage_bps             FLOAT,
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_archive_ticker ON signal_archive(ticker);
CREATE INDEX IF NOT EXISTS idx_signal_archive_strategy ON signal_archive(strategy);
CREATE INDEX IF NOT EXISTS idx_signal_archive_timestamp ON signal_archive(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_archive_order ON signal_archive(order_id);

-- KG version snapshots
CREATE TABLE IF NOT EXISTS kg_versions (
    id           SERIAL PRIMARY KEY,
    version_tag  TEXT,
    node_count   INT,
    edge_count   INT,
    source_agent TEXT,
    recorded_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kg_versions_recorded ON kg_versions(recorded_at DESC);

-- Hypothesis Board: quant hypotheses with full lifecycle tracking
CREATE TABLE IF NOT EXISTS hypotheses (
    id                SERIAL PRIMARY KEY,
    hypothesis_id     UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    title             TEXT NOT NULL,
    description       TEXT,
    primary_series    TEXT NOT NULL,
    benchmark_series  TEXT,
    regime_filter     TEXT,
    test_window_start DATE,
    test_window_end   DATE,
    status            TEXT NOT NULL DEFAULT 'IDEA',
    status_path       TEXT[] NOT NULL DEFAULT ARRAY['IDEA'],
    evidence          JSONB DEFAULT '[]'::jsonb,
    ic_comparison     JSONB,
    jobson_korkie     JSONB,
    regime_conditional JSONB,
    ai_synthesis      TEXT,
    backtest_run_id   UUID,
    paper_signal_weights JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    created_by        TEXT DEFAULT 'analytics-workspace'
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hypotheses_primary ON hypotheses(primary_series);
CREATE INDEX IF NOT EXISTS idx_hypotheses_created ON hypotheses(created_at DESC);

-- Hypothesis evidence attachments: pinned charts, test results, snapshots
CREATE TABLE IF NOT EXISTS hypothesis_evidence (
    id                SERIAL PRIMARY KEY,
    hypothesis_id     UUID NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    evidence_type     TEXT NOT NULL,  -- 'chart', 'test_result', 'interpretation', 'csv_export'
    tier              TEXT NOT NULL,  -- 'descriptive', 'diagnostic', 'predictive', 'prescriptive', 'cognitive'
    series_id         TEXT,
    label             TEXT,
    data              JSONB NOT NULL,
    attached_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_hid ON hypothesis_evidence(hypothesis_id);

-- Multiple testing correction tracking
CREATE TABLE IF NOT EXISTS hypothesis_test_log (
    id                SERIAL PRIMARY KEY,
    hypothesis_id     UUID NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    test_type         TEXT NOT NULL,   -- 'ic_t_test', 'jobson_korkie', 'granger_causality'
    raw_p_value       NUMERIC(10,6),
    bonferroni_p      NUMERIC(10,6),
    bh_corrected_p    NUMERIC(10,6),
    tests_in_family   INT NOT NULL DEFAULT 1,
    significant_raw   BOOLEAN,
    significant_bonf  BOOLEAN,
    significant_bh    BOOLEAN,
    test_detail       JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hypothesis_test_log_hid ON hypothesis_test_log(hypothesis_id);
-- ── Per-user settings vault ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR(64) NOT NULL UNIQUE,
    passphrase_hash  TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS broker_credentials (
    id                SERIAL PRIMARY KEY,
    owner_id          INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker            VARCHAR(16) NOT NULL,   -- alpaca | kraken
    nickname          VARCHAR(64) DEFAULT '',
    key_id            TEXT,
    secret_encrypted  TEXT NOT NULL,
    base_url          TEXT DEFAULT '',
    paper             BOOLEAN NOT NULL DEFAULT TRUE,
    is_active         BOOLEAN NOT NULL DEFAULT FALSE,
    last_verified_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_broker_creds_owner ON broker_credentials(owner_id, broker);
-- at most one active account per (owner, broker)
CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_creds_active
  ON broker_credentials(owner_id, broker) WHERE is_active;

CREATE TABLE IF NOT EXISTS user_api_keys (
    id             SERIAL PRIMARY KEY,
    owner_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider       VARCHAR(24) NOT NULL,   -- groq | featherless
    key_encrypted  TEXT NOT NULL,
    base_url       TEXT DEFAULT '',
    model          TEXT DEFAULT '',
    UNIQUE (owner_id, provider)
);

CREATE TABLE IF NOT EXISTS user_risk_prefs (
    id       SERIAL PRIMARY KEY,
    owner_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key      VARCHAR(64) NOT NULL,
    value    TEXT NOT NULL,
    UNIQUE (owner_id, key)
);
