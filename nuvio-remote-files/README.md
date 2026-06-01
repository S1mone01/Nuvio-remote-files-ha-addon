# <img src="icon.png" width="48" height="48" align="center"> Nuvio Remote Files

Trasforma il tuo Home Assistant in un server multimediale locale per **Stremio**. Indicizza automaticamente film e serie TV dai tuoi dischi USB collegati e li rende disponibili in streaming sulla tua rete locale, senza configurazioni complesse o esposizione a internet.

---

## 🚀 Funzionalità Principali

- **🏠 Integrazione Nativa HAOS**: Sfrutta il sistema di montaggio dischi di Home Assistant.
- **🛡️ Privacy Totale**: Funziona esclusivamente in locale (`http://IP_LOCALE`). Nessun dato lascia la tua rete.
- **✨ Auto-Organizer**: Metti i tuoi file "sporchi" nella cartella `downloads/` e l'addon li rinominerà e sposterà correttamente per te.
- **🎬 Metadati Automatici**: Recupera poster, trame e dettagli direttamente da TMDB.
- **📦 Zero Configurazione Link**: Rileva automaticamente l'IP del tuo Home Assistant per configurare Stremio.

---

## 🛠️ Guida alla Configurazione

### 1. Preparazione dei Contenuti
Puoi gestire i tuoi file in due modi:

#### A. Metodo Automatico (Consigliato)
Crea una cartella `downloads/` sul tuo disco USB e inserisci lì i tuoi file. L'addon li organizzerà automaticamente durante la scansione:
- `downloads/Film.Titolo.2023.1080p.mkv` → `movies/Film Titolo (2023) [1080p].mkv`

#### B. Metodo Manuale
Organizza i file seguendo questa struttura:
- `movies/Titolo Film (Anno) [Risoluzione].mkv`
- `series/Nome Serie/Season 01/S01E01 Titolo Episodio.mkv`

### 2. Impostazioni Add-on
Configura le seguenti opzioni nel pannello di Home Assistant:

| Opzione | Descrizione |
|---------|-------------|
| `media_disk_name` | Il nome del disco USB (es. `EXTERNAL_USB`). |
| `tmdb_api_key` | **Obbligatoria**. Ottienila gratuitamente su [themoviedb.org](https://www.themoviedb.org/). |
| `downloads_dir_name` | Cartella sorgente per l'Auto-Organizer (default: `downloads`). |
| `admin_scan_token` | Password per proteggere l'azione di scansione nel pannello Web. |

---

## 📺 Installazione in Stremio

1. Avvia l'add-on in Home Assistant.
2. Apri la **Web UI** dell'add-on.
3. Clicca sul pulsante **"Install Internal"**.
4. Stremio si aprirà automaticamente chiedendoti di confermare l'installazione.

---

## ❓ Risoluzione dei Problemi

- **Disco non rilevato**: Verifica il nome in *Impostazioni -> Sistema -> Hardware -> Dischi*. Deve corrispondere esattamente a `media_disk_name`.
- **Scansione non trova nulla**: Assicurati che i file abbiano l'estensione corretta (mkv, mp4, avi) e che il nome contenga l'anno (per i film) o il pattern `S01E01` (per le serie).
- **Auto-Organizer non sposta i file**: Controlla i log dell'add-on per verificare se ci sono errori di connessione a TMDB o problemi di permessi sul disco.

---

*Sviluppato con ❤️ per la community di Home Assistant.*
