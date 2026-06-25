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
    kraken_pair      VARCHAR(30),
    direction        VARCHAR(10),
    quantity         NUMERIC(18,6),
    fill_price       NUMERIC(18,6),
    fee_usd          NUMERIC(12,4),
    mode             VARCHAR(10),            -- paper | live
    signal_score     NUMERIC(8,4),
    kelly_fraction   NUMERIC(8,4),
    var_contribution NUMERIC(12,2),
    rejection_reason TEXT,
    raw_response     JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_audit_created ON order_audit(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_audit_ticker  ON order_audit(ticker);

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
