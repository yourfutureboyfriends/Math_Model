# ═══════════════════════════════════════════════════════════════════════════════
# Macro Research Platform — Production Dockerfile
# Multi-stage build for optimized production image
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ═══════════════════════════════════════════════════════════════════════════════
# Production stage
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.11-slim AS production

# Security: create non-root user
RUN groupadd -r macroapp && useradd -r -g macroapp -u 1000 macroapp

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    sqlite3 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Create required directories
RUN mkdir -p /app/database /app/reports/archive /app/logs /app/data/processed/live

# Copy application code
COPY --chown=macroapp:macroapp . .

# Set permissions
RUN chown -R macroapp:macroapp /app

# Switch to non-root user
USER macroapp

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/api/health/full || exit 1

# Expose port
EXPOSE 5000

# Run with gunicorn + eventlet (required for SocketIO)
CMD ["gunicorn", \
     "--worker-class", "eventlet", \
     "--workers", "1", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--access-logfile", "/app/logs/access.log", \
     "--error-logfile", "/app/logs/error.log", \
     "--capture-output", \
     "--enable-stdio-inheritance", \
     "main:app"]
