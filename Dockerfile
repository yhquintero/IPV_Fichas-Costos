# IPV Fichas y Costos - Dockerfile
# Multi-stage build for production optimization
# Autor: Ing. Yosvany Hernández Quintero

# ============================================
# Stage 1: Base image with Python
# ============================================
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Create app user for security
RUN groupadd -r ipvuser && useradd -r -g ipvuser -d /app -s /sbin/nologin ipvuser

# ============================================
# Stage 2: Dependencies
# ============================================
FROM base AS dependencies

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Runtime usa solo la librería estándar (requirements.txt documenta esto)
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "sqlcipher3-binary>=0.5"  # cifrado opcional (IPV_DB_KEY / IPV_DB_KEY_FILE)

# ============================================
# Stage 3: Production
# ============================================
FROM dependencies AS production

WORKDIR /app

# Copy application code
COPY server.py .
COPY auth.py .
COPY audit.py .
COPY rate_limiter.py .
COPY email_notifications.py .
COPY enterprise.py .
COPY security.py .
COPY dbcrypt.py .
COPY offsite.py .
COPY licencia.py .
COPY permisos.py .
COPY creador_licencias.py .
COPY keygen/ ./keygen/
COPY web/ ./web/
COPY docs/ ./docs/

# Create data directory
RUN mkdir -p /app/data /app/data/backups /app/certs \
    && chown -R ipvuser:ipvuser /app

# Copy startup script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Switch to non-root user
USER ipvuser

# Expose port
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import ssl,urllib.request as u; c=ssl.create_default_context(); c.check_hostname=False; c.verify_mode=ssl.CERT_NONE; u.urlopen('https://127.0.0.1:8443/api/health', context=c, timeout=5)" || exit 1

# Environment variables
ENV IPV_HOST=0.0.0.0 \
    PORT=8443 \
    IPV_DB_PATH=/app/data/ipv.db \
    IPV_RATE_LIMIT=120 \
    IPV_RATE_WINDOW=60

# Run the application
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "server.py"]

# ============================================
# Stage 4: Development (optional)
# ============================================
FROM dependencies AS development

WORKDIR /app

# Install development dependencies
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy all source code
COPY . .

# Create data directory
RUN mkdir -p /app/data /app/data/backups

# Expose port
EXPOSE 8000

# Development environment
ENV IPV_HOST=0.0.0.0 \
    PORT=8000 \
    IPV_DB_PATH=/app/data/ipv.db

# Run tests and start server
CMD ["python", "server.py"]
