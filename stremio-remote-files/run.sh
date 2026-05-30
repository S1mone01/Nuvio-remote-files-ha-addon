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

# Optional Disk Mounting
if bashio::config.has_value 'mount_device'; then
    MOUNT_DEVICE=$(bashio::config 'mount_device')
    MOUNT_PATH=$(bashio::config 'mount_path')
    
    # If mount_path is empty, use current media_disk_name
    if [ -z "$MOUNT_PATH" ]; then
        MOUNT_PATH="${MEDIA_DISK_NAME}"
    fi

    # We enforce mounting under /media because the app is hardcoded to look there
    if [[ ! "$MOUNT_PATH" =~ ^/media/ ]]; then
        # Remove leading slash if any to append to /media/
        CLEAN_PATH=$(echo "${MOUNT_PATH}" | sed 's|^/||')
        MOUNT_PATH="/media/${CLEAN_PATH}"
    fi

    bashio::log.info "Tentativo di montaggio: ${MOUNT_DEVICE} su ${MOUNT_PATH}..."
    mkdir -p "${MOUNT_PATH}"
    
    if mount "${MOUNT_DEVICE}" "${MOUNT_PATH}"; then
        bashio::log.info "Montaggio completato con successo."
        # Update MEDIA_DISK_NAME to be relative to /media for the app
        MEDIA_DISK_NAME=$(echo "${MOUNT_PATH}" | sed 's|/media/||')
        bashio::log.info "MEDIA_DISK_NAME aggiornato a: ${MEDIA_DISK_NAME}"
    else
        bashio::log.error "Impossibile montare ${MOUNT_DEVICE}. Verifica i permessi, il formato del disco o il percorso."
    fi
fi

# Get Local IP (using hostname -i for BusyBox compatibility)
INTERNAL_IP=$(hostname -i | awk '{print $1}')
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
