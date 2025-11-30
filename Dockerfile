# ============================================
# Stage 1: Build Rust extension
# ============================================
FROM python:3.11-slim AS rust-builder

RUN apt-get update && \
    apt-get install -y curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin
RUN pip install maturin

WORKDIR /build/rust_core

# Copy Rust source
COPY src/rust_core/ ./

# Build wheel - create empty dir if fails so COPY doesn't break
RUN maturin build --release || true
RUN mkdir -p /build/rust_core/target/wheels && touch /build/rust_core/target/wheels/.placeholder

# ============================================
# Stage 2: Build Node dependencies
# ============================================
FROM node:18-slim AS node-builder

WORKDIR /build
COPY autobumper/package*.json ./
RUN npm install --only=production

# ============================================
# Stage 3: Final runtime image
# ============================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pre-built Rust wheel and install (if exists)
COPY --from=rust-builder /build/rust_core/target/wheels/ /tmp/wheels/
RUN pip install /tmp/wheels/*.whl 2>/dev/null || echo "No Rust wheel - using Python fallback"
RUN rm -rf /tmp/wheels

# Copy Node modules for autobumper
COPY --from=node-builder /build/node_modules ./autobumper/node_modules

# Copy application source
COPY . .

# Create data directory
RUN mkdir -p /app/data

CMD ["python", "src/main.py"]
