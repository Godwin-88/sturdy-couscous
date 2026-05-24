The api, frontend, redis, and agent are all still in Created state — they never started because port 8000 was blocked. Now that you've killed that process, run:

  docker compose up -d --no-build

  Once that succeeds, your URLs will be:

  ┌─────────────────────────┬────────────────────────────┐
  │         Service         │            URL             │
  ├─────────────────────────┼────────────────────────────┤
  │ React UI (local Docker) │ http://localhost:5173      │
  ├─────────────────────────┼────────────────────────────┤
  │ React UI (Vercel)       │ your Vercel deployment URL │
  ├─────────────────────────┼────────────────────────────┤
  │ API                     │ http://localhost:8000      │
  ├─────────────────────────┼────────────────────────────┤
  │ API docs                │ http://localhost:8000/docs │
  ├─────────────────────────┼────────────────────────────┤
  │ Memgraph Lab            │ http://localhost:3000      │
  └─────────────────────────┴────────────────────────────┘

  ---
  Here's a rigorous test plan covering the full system:

  1. Infrastructure Health

  - GET http://localhost:8000/health → 200 OK
  - GET http://localhost:8000/docs → Swagger UI loads
  - Memgraph Lab at http://localhost:3000 connects and shows nodes loaded from master.cypher
  - Redis: docker exec graphalpha-redis redis-cli ping → PONG
  - Postgres: docker exec graphalpha-postgres pg_isready -U graphalpha → accepting connections

  2. Graph Data Integrity

  - In Memgraph Lab: MATCH (n) RETURN count(n) — should be > 0 (schema loaded)
  - MATCH ()-[r]->() RETURN count(r) — relationships exist
  - Query a known node type from master.cypher and verify properties are correct

  3. API Endpoints

  - Hit every endpoint listed in /docs with valid inputs, verify 2xx
  - Hit endpoints with missing/invalid payloads, verify 422 (not 500)
  - WebSocket: connect to ws://localhost:8000/ws (or whatever the WS route is), verify it stays open and emits data

  4. Agent Worker

  - docker logs graphalpha-agent — no crash/exception on startup
  - Trigger an agent action via the API and verify it writes back to Redis or Postgres
  - Let it run 60s and check logs again — confirm it's looping cleanly, not erroring

  5. Frontend → API Integration

  - Open http://localhost:5173, verify no console errors on load
  - Each panel loads data (no blank/spinner-stuck states): PnL dashboard, Signals table, Agent log, Graph canvas, Regime panel, Contradictions panel, Backtest panel
  - Graph canvas renders nodes (sigma.js) — zoom/pan works
  - WebSocket connection indicator shows connected (not disconnected)
  - Polling hooks refresh data without page reload

  6. Backtest (on-demand)

  docker compose --profile backtest up backtest
  docker logs graphalpha-backtest
  Verify it runs to completion and writes results to the backtest_results volume.
  
  7. CORS / Cross-Origin (Vercel frontend → local API)

  - Open the Vercel-deployed frontend in browser
  - Check browser DevTools Network tab — API calls to localhost:8000 should succeed (not blocked by CORS)
  - If CORS errors appear, verify FastAPI has CORSMiddleware allowing the Vercel origin

  8. Failure/Recovery

  - docker stop graphalpha-redis → verify API returns a clean error (not a 500 traceback)
  - docker start graphalpha-redis → agent-worker reconnects automatically (check logs)
  - Kill and restart graphalpha-api → frontend reconnects WebSocket within ~30s


