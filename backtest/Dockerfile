FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY agent/requirements.txt /tmp/agent-req.txt
RUN pip install --no-cache-dir -r /tmp/agent-req.txt

COPY backtest/ /app/backtest/
COPY agent/    /app/agent/

WORKDIR /app/backtest

ENTRYPOINT ["python", "engine.py"]
