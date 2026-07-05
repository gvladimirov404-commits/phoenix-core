# ==========================================
# Phoenix Core - Hardened Multi-stage Docker Build
# Security features:
#   - Non-root user
#   - Read-only root filesystem support
#   - Dropped Linux capabilities
#   - Minimal base image
#   - Multi-stage build
#   - Health checks
#   - No new privileges
# ==========================================

# --------------------
# Stage 1: Builder
# --------------------
FROM python:3.11-slim AS builder

# Install build dependencies (only what's needed)
RUN apt-get update && apt-get install -y --no-install-recommends     gcc     libffi-dev     && rm -rf /var/lib/apt/lists/*     && apt-get clean

WORKDIR /build

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --------------------
# Stage 2: Production (Hardened)
# --------------------
FROM python:3.11-slim AS production

# Security: Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Security: Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
# Security: Set Python path
ENV PATH=/home/phoenix/.local/bin:$PATH

# Security: Create non-root user with minimal privileges
RUN groupadd -r -g 1000 phoenix &&     useradd -r -u 1000 -g phoenix -d /app -s /sbin/nologin phoenix

# Security: Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     curl     ca-certificates     && rm -rf /var/lib/apt/lists/*     && apt-get clean     && apt-get autoremove -y

# Security: Set working directory with proper ownership
WORKDIR /app
RUN chown phoenix:phoenix /app

# Security: Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/data /app/tmp &&     chown -R phoenix:phoenix /app

# Copy installed packages from builder
COPY --from=builder --chown=phoenix:phoenix /root/.local /home/phoenix/.local

# Copy application code
COPY --chown=phoenix:phoenix phoenix_core/ ./phoenix_core/
COPY --chown=phoenix:phoenix config/ ./config/

# Security: Switch to non-root user
USER phoenix

# Security: Health check (non-privileged)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD python -c "import phoenix_core; print('OK')" || exit 1

# Security: Expose only necessary port
EXPOSE 8080

# Security: Use exec form for proper signal handling
CMD ["python", "-m", "phoenix_core"]

# --------------------
# Stage 3: Development
# --------------------
FROM production AS development

USER root

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends     git     vim     && rm -rf /var/lib/apt/lists/*

# Copy test files
COPY --chown=phoenix:phoenix tests/ ./tests/
COPY --chown=phoenix:phoenix requirements-dev.txt .
RUN pip install --no-cache-dir --user -r requirements-dev.txt

USER phoenix

CMD ["python", "-m", "pytest", "-v"]
