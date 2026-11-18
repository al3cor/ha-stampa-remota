<p align="center"><img src="custom_components/stampa_remota/brand/logo.png" width="110" alt="Stampa remota"></p>

<h1 align="center">Stampa remota per Home Assistant</h1>

<p align="center">Carichi un file dal telefono, anche fuori casa, e la stampante di casa lo stampa.<br>
<b>Integrazione HACS</b>: funziona anche con Home Assistant in Docker/Container o Core (nessuna app, niente Supervisor).</p>

Versione integrazione dell'app [Remote Print](https://github.com/Gapman1980/ha-remote-print) di Gapman1980 (MIT):
stesse funzioni, ma senza CUPS e senza container in più.

## Cosa fa

- Voce **Stampa** nel menu laterale di Home Assistant (grafica sobria, colori del tema di HA, chiaro e scuro): scegli il file, copie, bianco e nero, adatta al foglio, pagine e premi
  **STAMPA A CASA**. Funziona ovunque funzioni Home Assistant (app, Nabu Casa, VPN): passa dall'accesso di HA, nessuna porta aperta.
- Anche per gli utenti **non amministratori** (opzione "Pannello solo per gli amministratori" spenta).
- Accetta **PDF, foto (JPG, PNG, HEIC dell'iPhone) e testo**.
- Elenco delle ultime stampe con stato in tempo reale (In coda → Invio → Stampa → Stampato ✓), annulla, chi ha stampato.
- Livelli d'inchiostro/toner e avvisi della stampante (carta finita, inchiostro, sportello aperto).
- Azione **`stampa_remota.stampa`** per le automazioni: stampa un file, un indirizzo web o un testo.
- Evento **`stampa_remota_evento`** a ogni cambio di stato (per avvisi o automazioni).
- Se la stampante è spenta o occupata il lavoro resta in coda e riparte da solo (fino a 6 ore).

## Come funziona (senza CUPS)

```
telefono ─► Home Assistant (API autenticata) ─► conversione in Python ─► IPP ─► stampante
                                                  PDFium + Pillow
```

La stampante dichiara via IPP i formati che accetta e l'integrazione sceglie da sola:

| La stampante accetta | Cosa viene inviato |
|---|---|
| PDF | il PDF così com'è (foto e testo diventano PDF) |
| URF (AirPrint) | pagine disegnate con PDFium e codificate in Apple raster, **un solo lavoro** per tutte le pagine |
| solo JPEG | un JPEG per pagina (anche le foto vanno sempre in JPEG: 50 volte più leggero del raster) |

Pensato per le stampanti AirPrint che **non accettano PDF** (molte inkjet Canon, Epson, HP economiche).
Non serve nessun driver. Le laser Brother senza AirPrint (che nell'app originale usano `brlaser`) **non** sono supportate.

## Requisiti

- Stampante di rete con **AirPrint / IPP Everywhere** (quasi tutte quelle degli ultimi 10 anni), con IP fisso nel router.
- Home Assistant 2025.1 o successivo (qualsiasi tipo di installazione).

## Installazione

1. HACS → ⋮ → **Repository personalizzati** → `https://github.com/al3cor/ha-stampa-remota`, tipo **Integrazione**.
2. Cerca **Stampa remota** → Scarica → riavvia Home Assistant.
3. Impostazioni → Dispositivi e servizi → **Aggiungi integrazione** → Stampa remota.
4. Indirizzo della stampante: di solito `ipp://IP-STAMPANTE/ipp/print` (basta anche solo l'IP).
   Se non risponde prova `ipps://IP/ipp/print` oppure `ipp://IP/ipp`.

Al primo avvio Home Assistant scarica `pypdfium2` e `pillow-heif` (pacchetti già compilati, nessuna compilazione).

## Automazioni

```yaml
# stampa un PDF scaricato da internet
action: stampa_remota.stampa
data:
  url: https://example.com/modulo.pdf
  copie: 2
  bianco_nero: true
```

```yaml
# stampa un testo (es. la lista della spesa)
action: stampa_remota.stampa
data:
  nome: Lista della spesa
  testo: "{{ state_attr('todo.spesa', 'items') }}"
```

```yaml
# stampante a getto d'inchiostro ferma da tempo: una pagina ogni settimana per non far seccare le testine
triggers:
  - trigger: time
    at: "10:00:00"
conditions:
  - condition: time
    weekday: sun
actions:
  - action: stampa_remota.stampa
    data:
      nome: Pagina anti-essiccazione
      testo: "Pagina di manutenzione del {{ now().strftime('%d/%m/%Y') }}"
```

Per `file:` il percorso deve stare in `allowlist_external_dirs` (es. `/config/www`).

## Differenze dall'app originale

| | App Remote Print | Integrazione Stampa remota |
|---|---|---|
| Installazione | Store delle app (solo HA OS / Supervised) | HACS (anche Docker / Core) |
| Conversione | CUPS + Ghostscript in un container | Python (PDFium, Pillow) dentro HA |
| Utenti non amministratori | solo con `lan_access` dalla rete di casa, senza password | sì, con il login di HA, anche da fuori |
| Automazioni | no | azione `stampa_remota.stampa` + evento |
| File caricati | salvati su disco per N giorni | solo in memoria fino all'invio |
| Brother senza AirPrint (`brlaser`) | sì | no |
| Fronte/retro | sì | quando la stampante lo dichiara (prossima versione) |

---

MIT License · idea, conversione e icona da Remote Print di Gapman1980; pannello ridisegnato nello stile di Home Assistant.
