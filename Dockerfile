# Multi-stage build for smaller image (best practice)
FROM python:3.11-slim AS builder
# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
# Production stage
FROM python:3.11-slim
# Install runtime deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*
# Create non-root user (security best practice)
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app
COPY --from=builder /root/.local /app/.local
COPY app/ .
# Switch to non-root
USER appuser
# Healthcheck for app service
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/query/package/test || exit 1
# Expose port
EXPOSE 8000
# Use non-root user in CMD
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
