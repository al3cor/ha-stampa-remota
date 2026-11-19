<p align="center"><img src="custom_components/stampa_remota/brand/logo.png" width="110" alt="Stampa remota"></p>

<h1 align="center">Stampa remota per Home Assistant</h1>

<p align="center">Carichi un file dal telefono, anche fuori casa, e la stampante di casa lo stampa.<br>
<b>Integrazione HACS</b>: funziona anche con Home Assistant in Docker/Container o Core (nessuna app, niente Supervisor).</p>

Versione integrazione dell'app [Remote Print](https://github.com/Gapman1980/ha-remote-print) di Gapman1980 (MIT):
stesse funzioni, ma senza CUPS e senza container in più.

## Cosa fa

- Voce **Stampa** nel menu laterale di Home Assistant (grafica sobria, colori del tema di HA, chiaro e scuro): scegli il file,
  copie, bianco e nero, adatta al foglio, pagine e premi **Stampa**. Funziona ovunque funzioni Home Assistant (app, Nabu Casa,
  VPN): passa dall'accesso di HA, nessuna porta aperta.
- **Anteprima e posizione**: il foglio con il limite di stampa della tua stampante e la pagina sopra; verticale/orizzontale,
  scala dal 5 al 300 %, Adatta, Centra, 100 %, trascini la pagina col dito, frecce per sfogliare i PDF di più pagine.
  La stampa esce esattamente come nell'anteprima.
- **Più stampanti**: aggiungi l'integrazione una volta per stampante; il pannello mostra un selettore (ricordato su ogni telefono)
  e l'elenco dice dove è andata ogni stampa.
- Anche per gli utenti **non amministratori** (opzione "Pannello solo per gli amministratori" spenta), ognuno col suo login.
- Accetta **PDF, foto (JPG, PNG, HEIC dell'iPhone) e testo**.
- Elenco delle ultime stampe con stato in tempo reale, chi ha stampato, annulla, **cestino** per toglierne una e **Svuota**.
- Livelli d'inchiostro/toner e avvisi della stampante **in italiano** (carta finita, foglio inceppato, sportello aperto...).
  Se una stampa si ferma, il motivo compare sulla stampa stessa e parte l'evento per le notifiche.
- Indirizzo sbagliato? La configurazione dice **perché** (porta sbagliata, percorso, autenticazione IPP, TLS, stampante
  spenta, formati offerti) invece di un generico "non risponde".
- Azione **`stampa_remota.stampa`** per le automazioni: stampa un file, un indirizzo web o un testo, su una stampante a scelta.
- Evento **`stampa_remota_evento`** a ogni cambio di stato (`stato`, `avviso`, `errore`, `nome`, `stampante`, `utente`).
- Se la stampante è spenta o occupata il lavoro resta in coda e riparte da solo (fino a 6 ore).

## Come funziona (senza CUPS)

```
telefono ─► Home Assistant (API autenticata) ─► conversione in Python ─► IPP ─► stampante
                                                  PDFium + Pillow
```

La stampante dichiara via IPP i formati che accetta e l'integrazione sceglie da sola:

| La stampante accetta | Cosa viene inviato |
|---|---|
| PDF | il PDF così com'è; con l'anteprima, foto o testo: i fogli impaginati come PDF |
| URF (AirPrint) | pagine disegnate con PDFium in Apple raster, **un solo lavoro**, intestazione identica a macOS |
| PWG raster (IPP Everywhere) | pagine in PWG raster, un solo lavoro |
| JPEG | un JPEG per foglio (le foto vanno sempre in JPEG quando si può: 50 volte più leggero del raster) |

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

## Differenze dall'app originale (Remote Print 1.6.0)

| | App Remote Print | Integrazione Stampa remota |
|---|---|---|
| Installazione | Store delle app (solo HA OS / Supervised) | HACS (anche Docker / Core) |
| Conversione | CUPS + Ghostscript in un container | Python (PDFium, Pillow) dentro HA |
| Anteprima, scala, posizione | sì (1.4.0) | sì |
| Più stampanti | sì (1.3.0) | sì, una voce per stampante |
| Cestino e Svuota | sì (1.4.1) | sì |
| Diagnosi dell'indirizzo | nel Registro dell'app (1.5.1) | nel modulo di configurazione |
| Intestazione URF come macOS | sì (1.6.0, filtro su CUPS) | sì, scritta così dall'inizio |
| Utenti non amministratori | elenco di nomi (1.5.0) | tutti gli utenti di HA, oppure solo amministratori |
| Automazioni, evento, avvisi in italiano | no | sì |
| File caricati | salvati su disco per N giorni | solo in memoria (anteprima: 30 minuti) |
| Brother laser senza AirPrint (`brlaser`) | sì | no (serve un driver CUPS) |
| Fronte/retro | sì | non ancora |

---

MIT License · idea, conversione e icona da Remote Print di Gapman1980; pannello ridisegnato nello stile di Home Assistant.
