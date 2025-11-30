# syntax=docker/dockerfile:1.4

# ============================================
# Stage 1: Build Rust extension
# ============================================
FROM python:3.11-slim AS rust-builder

RUN apt-get update && \
    apt-get install -y curl build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Rust (cached in layer)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin
RUN pip install maturin

WORKDIR /build

# Copy only Rust source (changes less frequently)
COPY src/rust_core/ ./rust_core/

# Build wheel with cache mount for cargo
WORKDIR /build/rust_core
RUN --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/build/rust_core/target \
    maturin build --release || echo "Rust build failed - will use Python fallback"

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

# Install only runtime dependencies (no build tools = smaller image)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached when requirements.txt unchanged)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy pre-built Rust wheel and install (if build succeeded)
RUN --mount=type=bind,from=rust-builder,source=/build/rust_core/target/wheels,target=/wheels \
    pip install /wheels/*.whl 2>/dev/null || echo "No Rust wheel - using Python fallback"

# Copy Node modules for autobumper
COPY --from=node-builder /build/node_modules ./autobumper/node_modules

# Copy application source last (changes most frequently)
COPY . .

# Create data directory
RUN mkdir -p /app/data

CMD ["python", "src/main.py"]
