.PHONY: up down logs load-graph verify shell-memgraph shell-api test backtest deploy up-risk-engine

# ── Local development ─────────────────────────────────────────────────────────
up:
	@echo "Building and starting all services..."
	docker compose up -d --build memgraph postgres redis api agent-worker frontend
	@echo "Waiting for graph loader..."
	@docker compose run --rm graph-loader
	@echo ""
	@echo "GraphAlpha is running:"
	@echo "  Frontend : http://localhost:5173"
	@echo "  API      : http://localhost:8000/docs"
	@echo "  Memgraph : http://localhost:3000"

up-risk-engine:
	@echo "Starting risk-engine service..."
	docker compose --profile cpp up -d --build risk-engine
	@echo "risk-engine started. Logs: docker compose logs risk-engine"

up-all:
	@echo "Building and starting all services..."
	docker compose up -d --build
	@echo "Waiting for graph loader..."
	@docker compose run --rm graph-loader
	@echo ""
	@echo "GraphAlpha is running:"
	@echo "  Frontend     : http://localhost:5173"
	@echo "  API          : http://localhost:8000/docs"
	@echo "  Memgraph     : http://localhost:3000"
	@echo "  RiskEngine   : see docker compose logs risk-engine"

up-monitoring:
	docker compose --profile monitoring up -d --build
	@echo "Prometheus: http://localhost:9090  Grafana: http://localhost:3001"

down:
	docker compose down

restart-api:
	docker compose restart api agent-worker

logs:
	docker compose logs -f api agent-worker

logs-agent:
	docker compose logs -f agent-worker

# ── Knowledge Graph ───────────────────────────────────────────────────────────
load-graph:
	docker compose run --rm graph-loader

verify-graph:
	docker compose exec memgraph mgconsole --host localhost --port 7687 \
		--execute "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count ORDER BY count DESC;"

shell-memgraph:
	docker compose exec memgraph mgconsole --host localhost --port 7687

# ── Development shells ────────────────────────────────────────────────────────
shell-api:
	docker compose exec api bash

shell-agent:
	docker compose exec agent-worker bash

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	docker compose exec api pytest /app/tests -v

test-agents:
	docker compose exec api pytest /app/tests/test_agents.py -v

# ── Backtesting ───────────────────────────────────────────────────────────────
backtest:
	docker compose --profile backtest run --rm backtest python engine.py \
		--start 2021-01-01 --end 2023-12-31 --use-graph

backtest-ablation:
	@echo "Running KG-grounded vs ungrounded comparison..."
	docker compose --profile backtest run --rm backtest python engine.py \
		--start 2021-01-01 --end 2023-12-31 --use-graph > /tmp/grounded.json
	docker compose --profile backtest run --rm backtest python engine.py \
		--start 2021-01-01 --end 2023-12-31 --no-graph > /tmp/ungrounded.json
	@echo "=== KG-Grounded ===" && cat /tmp/grounded.json
	@echo "=== Ungrounded ===" && cat /tmp/ungrounded.json

# ── Production deployment (run on Vultr VM) ───────────────────────────────────
deploy:
	git pull origin main
	docker compose -f docker-compose.yml -f docker-compose.prod.yml \
		--profile monitoring up -d --build
	@echo "Production deployed. API: http://$(hostname -I | awk '{print $$1}'):8000"

deploy-no-monitoring:
	git pull origin main
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# ── Paper → Live trading gate ─────────────────────────────────────────────────
enable-live-trading:
	@echo "WARNING: This enables LIVE trading with real capital."
	@read -p "Type CONFIRM to proceed: " confirm; \
	if [ "$$confirm" = "CONFIRM" ]; then \
		sed -i 's/KRAKEN_TRADING_MODE=paper/KRAKEN_TRADING_MODE=live/' .env; \
		docker compose restart agent-worker; \
		echo "Live trading enabled."; \
	else \
		echo "Aborted."; \
	fi
