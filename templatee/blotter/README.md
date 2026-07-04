# Menu 8 Blotter — Backoffice

Transaction ledger, P&L tracking, and performance attribution for the Transact application. Implements **double-entry journaling** and a Chart Area (Overview) with live data from **Nautilus** when configured.

## Data source: Nautilus (not Deriv)

- **Trading and chart data** for the Blotter come from **Nautilus Trader** live integration (DataClient / DataCatalog), not from Deriv API. Deriv remains for synthetic derivatives only (see TRANSACT_APP_SPEC.md).
- Chart OHLCV bars and instrument lists: `app/blotter/chart_data.py` uses Nautilus when `NAUTILUS_CATALOG_PATH` (or `NAUTILUS_DATA_CATALOG_PATH`) is set; otherwise falls back to yfinance for development.
- Set `DATABASE_URL` for persistent ledger and trades (Postgres).

## Double-entry accounting

- **Rules:** Every journal entry has two or more lines; total debits = total credits. Assets increase with debit; liabilities/equity with credit. Income: credit; Expense: debit.
- **Tables:** `accounts`, `journal_entries`, `journal_lines`, `trades` (see `app/accounting/models.py`). Seed accounts: Cash (1000), Securities (2000), Realized P&L (3000), Unrealized P&L (4000), Commission/Expense (5000).
- **Trade mapping:** Buy → Dr Securities, Cr Cash. Sell → Dr Cash, Cr Securities (and Realized P&L as needed to balance).
- **Ledger service:** `app/accounting/ledger.py` — `create_trade_entry`, `get_ledger`, `get_account_balances`.

## Mathematical references (M1–M7)

- **Performance attribution** (`app/blotter/attribution.py`): M1 §4 (Sharpe, Treynor), M2 factor decomposition. Formula: `r_p = α + β_p·r_m + Σ_k λ_k·β_{p,k} + ε_p`. CAPM alpha, systematic return, factor contributions, residual.
- **Blotter concepts:** See `knowledge_base/menus/blotter/concepts.cypher` (Brinson attribution, implementation shortfall, P&L attribution, etc.).
- **Spec:** TRANSACT_APP_SPEC.md § 3.8 (Menu 8 key features), § 8.3 (Nautilus execute/backtest/tearsheet).

## Sub-menus (key features)

1. **Chart Area (Overview)** — Live charts: candlestick, bar, line, Heikin-Ashi, volume; timeframe; indicators (SMA/EMA, Bollinger, RSI, MACD); pattern reference. Data from Nautilus-backed endpoints.
2. **Trade Entry** — Record trades; persisted to Postgres + ledger when `DATABASE_URL` is set.
3. **Position Monitor** — Open positions with unrealized P&L.
4. **P&L Attribution** — Alpha, beta, factor, residual decomposition (M1/M2).
5. **Transaction History** — Full trade list; optional date filter.
6. **Export** — CSV/JSON export of trades and positions with date range.

## Endpoints

- `GET /blotter/chart/bars`, `GET /blotter/instruments` — Chart data (Nautilus or yfinance).
- `POST /blotter/trade` — Add trade (writes to DB + ledger when `DATABASE_URL` set).
- `GET /blotter/positions`, `POST /blotter/positions` — Positions with P&L.
- `GET /blotter/history` — Trades (optional `from_date`, `to_date`, `asset`).
- `GET /blotter/journal`, `GET /blotter/accounts` — Ledger view (require `DATABASE_URL`).
- `POST /blotter/attribution`, `POST /blotter/pnl` — Attribution and P&L.
