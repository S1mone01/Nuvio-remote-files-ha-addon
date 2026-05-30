#!/usr/bin/env bashio

# Read configuration
export PORT=$(bashio::config 'port')
export TMDB_API_KEY=$(bashio::config 'tmdb_api_key')
export ADMIN_SCAN_TOKEN=$(bashio::config 'admin_scan_token')
export SCAN_CRON=$(bashio::config 'scan_cron')
export TRUSTED_NETWORKS=$(bashio::config 'trusted_networks')

MOVIES_DIR=$(bashio::config 'movies_dir_name')
SERIES_DIR=$(bashio::config 'series_dir_name')
MEDIA_DISK_NAME=$(bashio::config 'media_disk_name')
SUBPATH=$(bashio::config 'media_subpath')

# Get Local IP
INTERNAL_IP=$(ip route get 1.1.1.1 | awk '/src/ {print $7}')
if [ -z "$INTERNAL_IP" ]; then
    # Fallback for systems where awk index might differ or ip route fails
    INTERNAL_IP=$(hostname -i | awk '{print $1}')
fi
MEDIA_BASE_URL="http://${INTERNAL_IP}:${PORT}"
bashio::log.info "URL base rilevato: ${MEDIA_BASE_URL}"

# Map paths for the Python application
BASE_REL_PATH="${MEDIA_DISK_NAME}"
if [ -n "$SUBPATH" ]; then
    BASE_REL_PATH="${BASE_REL_PATH}/${SUBPATH}"
fi

export MOVIES_DIR_NAME="${BASE_REL_PATH}/${MOVIES_DIR}"
export SERIES_DIR_NAME="${BASE_REL_PATH}/${SERIES_DIR}"
export MEDIA_BASE_URL_INTERNAL="${MEDIA_BASE_URL}"
export MEDIA_BASE_URL_EXTERNAL="${MEDIA_BASE_URL}"

# Background scanner loop
(
    bashio::log.info "Avvio scanner automatico (ogni ora)..."
    sleep 15 # Attesa avvio server
    while true; do
        bashio::log.info "Esecuzione scansione programmata..."
        curl -s -X POST "http://localhost:${PORT}/admin/scan" \
             -H "Authorization: Bearer ${ADMIN_SCAN_TOKEN}" > /dev/null
        sleep 3600
    done
) &

# Run uvicorn
bashio::log.info "Avvio server FastAPI su porta ${PORT}..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
