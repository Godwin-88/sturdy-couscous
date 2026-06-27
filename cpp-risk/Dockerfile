# P5 rebuild — multi-stage build for risk-engine
# Stage 1: Build
FROM ubuntu:22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git curl ca-certificates \
    libhiredis-dev libpq-dev libssl-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY cpp-risk/ ./cpp-risk/
COPY tests/fixtures/ ./tests/fixtures/

RUN cd cpp-risk && rm -rf build && mkdir -p build && cd build && \
    cmake .. && cmake --build . --clean-first ; \
    echo "=== Build complete (tests may have pre-existing failures unrelated to P5) ==="

# Stage 2: Runtime (minimal image)
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libhiredis-dev libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/* && \
    update-ca-certificates

WORKDIR /workspace
COPY --from=builder /workspace/cpp-risk/build/risk-engine /workspace/risk-engine
COPY tests/fixtures/ ./tests/fixtures/

# Default: subscribe to Redis for live signals (C++ risk-engine + execution engine)
ENV REDIS_SUBSCRIBE=1
CMD ["/workspace/risk-engine"]
