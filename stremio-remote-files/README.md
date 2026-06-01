# Stremio Remote Files - Home Assistant Add-on

Questo add-on trasforma il tuo Home Assistant in un server Stremio locale. Indicizza i film e le serie TV presenti sui tuoi dischi USB collegati ad HAOS e li rende disponibili su Stremio tramite la tua rete LAN.

## Funzionalità
- **Nativo HAOS**: Si integra perfettamente con il sistema di montaggio dischi di Home Assistant.
- **Solo Locale**: Nessuna esposizione a internet, nessun certificato HTTPS richiesto (uso su `http://IP_LOCALE`).
- **Auto-configurante**: Rileva automaticamente l'IP locale per i link di streaming.
- **Auto-Organizer**: Sposta e rinomina automaticamente i file "sporchi" (es. dai download) nella struttura corretta durante la scansione.

## Configurazione

### 1. Preparazione dei Media
Puoi organizzare i file manualmente o usare la funzione **Auto-Organizer**:

#### Metodo Automatico (Consigliato)
Inserisci i tuoi file (anche con nomi disordinati) nella cartella `downloads/`. L'addon li riconoscerà, li sposterà e li rinominerà correttamente per te.
Esempio: `downloads/Film.Titolo.2023.1080p.mkv` -> `movies/Film Titolo (2023) [1080p].mkv`

#### Metodo Manuale
Assicurati che i tuoi film e serie siano organizzati in questo modo sul disco USB:
- `movies/Movie Title (YYYY) [1080p].mkv`
- `series/Series Name/Season 01/S01E01 Title.mkv`

### 2. Opzioni dell'Add-on
- `media_disk_name`: Il nome del disco USB come appare in Home Assistant (controlla in Impostazioni -> Sistema -> Hardware -> Dischi o guarda sotto `/media` nel File Editor).
- `media_subpath`: (Opzionale) Se i tuoi media sono in una sottocartella (es. "Media"), inseriscila qui.
- `downloads_dir_name`: Il nome della cartella dove metti i file da organizzare (default: `downloads`).
- `tmdb_api_key`: Obbligatoria per scaricare poster e trame. Ottienila su [themoviedb.org](https://www.themoviedb.org/documentation/api).
- `admin_scan_token`: Una password a tua scelta per proteggere l'azione di scansione.

### 3. Installazione in Stremio
Una volta avviato l'add-on:
1. Apri l'interfaccia utente (Web UI).
2. Clicca su "Install Internal".
3. Stremio si aprirà e ti chiederà di installare l'addon.

## Risoluzione dei Problemi
- **Disco non trovato**: Verifica che il nome del disco sia corretto. In HAOS i dischi sono montati in `/media/<NOME_DISCO>`.
- **Scansione vuota**: Controlla che i nomi dei file seguano il formato supportato (es. `Titolo (Anno)`).
