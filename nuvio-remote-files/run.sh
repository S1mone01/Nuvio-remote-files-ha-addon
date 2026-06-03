#!/usr/bin/env bashio

# Read configuration
export PORT=$(bashio::config 'port')
export TMDB_API_KEY=$(bashio::config 'tmdb_api_key')
export ADMIN_SCAN_TOKEN=$(bashio::config 'admin_scan_token')
export TRUSTED_NETWORKS=$(bashio::config 'trusted_networks')

MOVIES_DIR=$(bashio::config 'movies_dir_name')
SERIES_DIR=$(bashio::config 'series_dir_name')
DOWNLOADS_DIR=$(bashio::config 'downloads_dir_name')
export MEDIA_DISK_NAME=$(bashio::config 'media_disk_name')
export FILTER_MKV_TRACKS=$(bashio::config 'filter_mkv_tracks')
SUBPATH=$(bashio::config 'media_subpath')
MEDIA_BASE_URL_CONFIG=$(bashio::config 'media_base_url')

# Configure Base URL if provided
if [ -n "$MEDIA_BASE_URL_CONFIG" ] && [ "$MEDIA_BASE_URL_CONFIG" != "null" ]; then
    export MEDIA_BASE_URL_INTERNAL="${MEDIA_BASE_URL_CONFIG}"
    export MEDIA_BASE_URL_EXTERNAL="${MEDIA_BASE_URL_CONFIG}"
    bashio::log.info "URL base configurato: ${MEDIA_BASE_URL_INTERNAL}"
else
    bashio::log.info "URL base non configurato, verrà rilevato dinamicamente dalle richieste."
fi

# Map paths for the Python application
BASE_REL_PATH="${MEDIA_DISK_NAME}"
if [ -n "$SUBPATH" ]; then
    BASE_REL_PATH="${BASE_REL_PATH}/${SUBPATH}"
fi

export MOVIES_DIR_NAME="${BASE_REL_PATH}/${MOVIES_DIR}"
export SERIES_DIR_NAME="${BASE_REL_PATH}/${SERIES_DIR}"
export DOWNLOADS_DIR_NAME="${BASE_REL_PATH}/${DOWNLOADS_DIR}"

# Run uvicorn
bashio::log.info "Avvio server FastAPI su porta ${PORT}..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}" --limit-concurrency 4
