FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY agent/requirements.txt /tmp/agent-req.txt
COPY backtest/requirements.txt /tmp/backtest-req.txt
RUN pip install --no-cache-dir -r /tmp/agent-req.txt && \
    pip install --no-cache-dir -r /tmp/backtest-req.txt

COPY agent/    /app/agent/
COPY backtest/ /app/backtest/

WORKDIR /app/backtest

ENTRYPOINT ["python", "-m", "unittest", "tests.test_p2", "-v"]
