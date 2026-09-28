#!/bin/bash
# IPV Fichas y Costos - Docker Entrypoint
# Handles initialization and certificate generation

set -e

echo "═══════════════════════════════════════════════════"
echo "  IPV · Fichas y Costos v1.0"
echo "  Initializing..."
echo "═══════════════════════════════════════════════════"

# Create data directories
mkdir -p /app/data /app/data/backups /app/certs

# Generate self-signed certificates if not present
if [ ! -f /app/certs/ipv-server-cert.pem ]; then
    echo "Generating self-signed certificates..."
    openssl req -x509 -newkey rsa:2048 -keyout /app/certs/ipv-server-key.pem \
        -out /app/certs/ipv-server-cert.pem -days 365 -nodes \
        -subj "/CN=sqlserver/O=IPV Fichas y Costos/C=CU" \
        -addext "subjectAltName=DNS:sqlserver,DNS:localhost,IP:127.0.0.1" 2>/dev/null
    
    echo "✓ Certificates generated"
fi

# Set certificate environment variables
export IPV_TLS_CERT=/app/certs/ipv-server-cert.pem
export IPV_TLS_KEY=/app/certs/ipv-server-key.pem

# Initialize database if not present
if [ ! -f /app/data/ipv.db ]; then
    echo "Initializing database..."
    python -c "import server; server.init_db()"
    echo "✓ Database initialized"
fi

# Create backup on startup
echo "Backups gestionados por el servidor (inicio + programados)."

# Print configuration
echo ""
echo "Configuration:"
echo "  Host: ${IPV_HOST:-0.0.0.0}"
echo "  Port: ${PORT:-8443}"
echo "  Database: ${IPV_DB_PATH:-/app/data/ipv.db}"
echo "  TLS: ✓"
echo "  Auth: $([ -n "$IPV_API_TOKEN" ] && echo "✓" || echo "✗")"
echo "  Rate Limit: ${IPV_RATE_LIMIT:-120}/${IPV_RATE_WINDOW:-60}s"
echo ""
echo "═══════════════════════════════════════════════════"
echo "  Starting server..."
echo "═══════════════════════════════════════════════════"

# Execute the main command
exec "$@"
