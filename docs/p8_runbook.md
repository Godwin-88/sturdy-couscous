# GraphAlpha — Personal Live Trading Operating Procedure (Runbook)

## Quick Reference

| Venue | Status | P&L Source |
|-------|--------|------------|
| Kraken | Live (post-P7) | Real account via `KRAKEN_TRADING_MODE=live` |
| IBKR | Paper only | Simulated via IB Gateway |

**WARNING:** Never confuse IBKR paper P&L with real money. Only Kraken trades are live.

---

## 1. Daily Startup

```bash
# Start all services
make up

# Verify graph loaded
make verify-graph

# Check current trading mode
grep KRAKEN_TRADING_MODE .env
```

Expected output: `KRAKEN_TRADING_MODE=paper` (safe default).

---

## 2. Enabling Live Trading (Kraken Only)

```bash
# Confirm you want live trading
export KRAKEN_TRADING_MODE=live

# Restart risk-engine to pick up new mode
docker-compose restart risk-engine

# Verify loud logging
docker-compose logs risk-engine | grep "Initialised (mode=live)"
```

**Safety:** API keys must be set in `.env` as `KRAKEN_API_KEY` and `KRAKAN_API_SECRET`.

---

## 3. Monitoring Dashboard Halt States

### Halt Types and Responses

| Halt Type | Cause | Action |
|-----------|-------|--------|
| Circuit breaker | Drawdown > 10% from peak | Wait for recovery or add funds; do not override |
| Kill switch | `KILL_SWITCH=1` set | Unset `KILL_SWITCH` and restart `risk-engine` |
| Reconciliation mismatch | Position count differs from Kraken | Run `clear_reconciliation_halt` via C++ API, then manually verify positions |

### Checking Halt State

```bash
# Via Redis
docker-compose exec redis redis-cli GET graphalpha:agent_status

# Via API
curl http://localhost:8000/api/positions/status
```

---

## 4. Reconciliation Mismatch Procedure

If Kraken reports different positions than internal state:

1. **Do not panic** — Trading is halted automatically (`kraken_live_halt_=true`)
2. **Verify discrepancy:**
   ```bash
   # Check live account positions (via Kraken API in paper mode)
   docker-compose logs risk-engine | grep "reconcile_positions"
   ```
3. **Acknowledge and resync:**
   - Manually compare open positions on Kraken web UI
   - If discrepancy is resolved (e.g., timing difference), set `KRAKEN_REENABLE=1` in `.env` and restart risk-engine
   - RiskEngine will then call `clear_reconciliation_halt()` on next signal cycle
4. **Document in audit:**
   ```sql
   SELECT * FROM live_validation_discrepancy ORDER BY created_at DESC LIMIT 10;
   ```

**Note:** Requires explicit `KRAKEN_REENABLE=1` environment variable to clear halt — no auto-recovery.

---

## 5. Safe Shutdown

```bash
# Gracefully stop the risk engine
docker-compose stop risk-engine

# Confirm pending orders flushed (no open positions in paper mode)
docker-compose logs risk-engine | grep "shutdown"
```

Positions are persisted to `portfolio_state` table on every update.

---

## 6. Emergency Procedures

### Kill Switch (Immediate Halt)

```bash
# Set kill switch
echo "KILL_SWITCH=1" >> .env
docker-compose restart risk-engine
```

### Force Kill

```bash
# If graceful shutdown fails
docker-compose kill risk-engine
```

---

## 7. Validation Period Controls

During P7 live validation period:

- `LIVE_VALIDATION_SCALE_PCT` < 100 scales position sizes
- Default: unset = 100% (full size)
- Example: `LIVE_VALIDATION_SCALE_PCT=10` for 10% size

Set before starting live mode:

```bash
echo "LIVE_VALIDATION_SCALE_PCT=10" >> .env
```

---

## 8. Verifying System Health

```bash
# Check all services running
docker-compose ps

# Check Redis message flow
docker-compose exec redis redis-cli LLEN graphalpha:signals:v1

# Check Postgres for recent trades
docker-compose exec postgres psql -d graphalpha -c "SELECT count(*) FROM order_audit WHERE created_at > NOW() - interval '1 hour';"
```

---

## 9. Logs and Debugging

```bash
# Risk engine logs
docker-compose logs -f risk-engine

# Agent worker logs
docker-compose logs -f agent-worker

# PostgreSQL position view
docker-compose exec postgres psql -d graphalpha -c "SELECT * FROM portfolio_state;"
```