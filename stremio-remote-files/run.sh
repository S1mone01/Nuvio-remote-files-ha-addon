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
MEDIA_SUBPATH=$(bashio::config 'media_subpath')

# Construct full media path for check
MEDIA_PATH="/media/${MEDIA_DISK_NAME}"
SUBPATH=$(bashio::config 'media_subpath')
if [ -n "$SUBPATH" ]; then
    MEDIA_PATH="${MEDIA_PATH}/${SUBPATH}"
fi

# Wait for media disk to be mounted
bashio::log.info "Verifica montaggio disco: ${MEDIA_PATH}"
while [ ! -d "${MEDIA_PATH}" ]; do
    bashio::log.warning "Disco non trovato! In attesa di: ${MEDIA_PATH}"
    sleep 10
done
bashio::log.info "Disco montato correttamente."

# Get Local IP
INTERNAL_IP=$(hostname -I | awk '{print $1}')
MEDIA_BASE_URL="http://${INTERNAL_IP}:${PORT}"

bashio::log.info "URL base rilevato: ${MEDIA_BASE_URL}"

# Map paths for the Python application
# The app logic is: root = Path("/media") / MOVIES_DIR_NAME
BASE_REL_PATH="${MEDIA_DISK_NAME}"
if [ -n "$SUBPATH" ]; then
    BASE_REL_PATH="${BASE_REL_PATH}/${SUBPATH}"
fi

export MOVIES_DIR_NAME="${BASE_REL_PATH}/${MOVIES_DIR}"
export SERIES_DIR_NAME="${BASE_REL_PATH}/${SERIES_DIR}"
export MEDIA_BASE_URL_INTERNAL="${MEDIA_BASE_URL}"
export MEDIA_BASE_URL_EXTERNAL="${MEDIA_BASE_URL}"

# Log envs for debug (except keys)
bashio::log.info "Movies subfolder: /media/${MOVIES_DIR_NAME}"
bashio::log.info "Series subfolder: /media/${SERIES_DIR_NAME}"

# Background scanner loop
(
    bashio::log.info "Scanner background loop avviato."
    # Wait for uvicorn to start
    sleep 15
    while true; do
        bashio::log.info "Esecuzione scansione programmata..."
        curl -s -X POST "http://localhost:${PORT}/admin/scan" \
             -H "Authorization: Bearer ${ADMIN_SCAN_TOKEN}" > /dev/null
        
        bashio::log.info "Scansione completata. Prossima tra 1 ora."
        sleep 3600
    done
) &

# Run uvicorn
bashio::log.info "Avvio server FastAPI su porta ${PORT}..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
