# P5 rebuild
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git curl ca-certificates \
    libhiredis-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY cpp-risk/ ./cpp-risk/
COPY tests/fixtures/ ./tests/fixtures/

RUN cd cpp-risk && rm -rf build && mkdir -p build && cd build && \
    cmake .. && cmake --build . --clean-first && ctest --output-on-failure
